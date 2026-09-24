from rest_framework import serializers
from .models import (
    ClassCourse, ScheduleEntry, Conflict, SwapRequest, Substitute,
    TeacherSuspension
)
from .suspensions import (
    get_active_suspensions, find_suspension_for_entry
)


class ClassCourseSerializer(serializers.ModelSerializer):
    course_name = serializers.CharField(source='course.name', read_only=True)
    teacher_name = serializers.CharField(source='teacher.name', read_only=True)
    class_name = serializers.CharField(source='class_id.name', read_only=True)
    weekly_hours = serializers.IntegerField(source='course.weekly_hours', read_only=True)

    class Meta:
        model = ClassCourse
        fields = '__all__'


class ScheduleEntrySerializer(serializers.ModelSerializer):
    course_name = serializers.CharField(source='course.name', read_only=True)
    teacher_name = serializers.CharField(source='teacher.name', read_only=True)
    classroom_name = serializers.CharField(source='classroom.name', read_only=True)
    class_name = serializers.CharField(source='class_id.name', read_only=True)

    class Meta:
        model = ScheduleEntry
        fields = '__all__'


class ScheduleEntryDetailSerializer(serializers.ModelSerializer):
    course_name = serializers.CharField(source='course.name', read_only=True)
    teacher_name = serializers.CharField(source='teacher.name', read_only=True)
    classroom_name = serializers.CharField(source='classroom.name', read_only=True)
    class_name = serializers.CharField(source='class_id.name', read_only=True)
    original_teacher_name = serializers.CharField(
        source='original_teacher.name', read_only=True, allow_null=True
    )
    # 命中教师临时停排时段时给出标记，供前端单独提示
    suspension_conflict = serializers.SerializerMethodField()
    suspension_reason = serializers.SerializerMethodField()
    suspension_date = serializers.SerializerMethodField()

    _suspension_cache = None

    class Meta:
        model = ScheduleEntry
        fields = '__all__'

    # 列表序列化时按学期在 root 上缓存生效中的停排，避免逐条查库
    def _get_suspensions(self, semester_id):
        root = self.root
        cache = getattr(root, '_suspensions_by_semester', None)
        if cache is None:
            cache = {}
            setattr(root, '_suspensions_by_semester', cache)
        if semester_id not in cache:
            from core.models import Semester
            try:
                semester = Semester.objects.get(id=semester_id)
            except Semester.DoesNotExist:
                cache[semester_id] = []
            else:
                cache[semester_id] = get_active_suspensions(semester)
        return cache[semester_id]

    def _matched_suspension(self, obj):
        suspensions = self._get_suspensions(obj.semester_id)
        return find_suspension_for_entry(suspensions, obj)

    def get_suspension_conflict(self, obj):
        return self._matched_suspension(obj) is not None

    def get_suspension_reason(self, obj):
        s = self._matched_suspension(obj)
        return s.reason if s else None

    def get_suspension_date(self, obj):
        s = self._matched_suspension(obj)
        return s.date.isoformat() if s else None


class ConflictSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conflict
        fields = '__all__'


class SwapRequestSerializer(serializers.ModelSerializer):
    requesting_teacher_name = serializers.CharField(
        source='requesting_teacher.name', read_only=True
    )
    target_teacher_name = serializers.CharField(
        source='target_teacher.name', read_only=True
    )

    class Meta:
        model = SwapRequest
        fields = '__all__'


class SubstituteSerializer(serializers.ModelSerializer):
    original_teacher_name = serializers.CharField(
        source='original_teacher.name', read_only=True
    )
    substitute_teacher_name = serializers.CharField(
        source='substitute_teacher.name', read_only=True
    )

    class Meta:
        model = Substitute
        fields = '__all__'


class TeacherSuspensionSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source='teacher.name', read_only=True)
    semester_name = serializers.CharField(source='semester.name', read_only=True)
    period_count = serializers.IntegerField(read_only=True)
    day_of_week = serializers.IntegerField(read_only=True)

    class Meta:
        model = TeacherSuspension
        fields = '__all__'


class TeacherSuspensionCreateSerializer(serializers.Serializer):
    teacher = serializers.IntegerField()
    semester = serializers.IntegerField()
    date = serializers.DateField()
    start_period = serializers.IntegerField(min_value=1)
    period_count = serializers.IntegerField(min_value=1, help_text='连续几节')
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)

    def validate(self, attrs):
        from core.models import Teacher, Semester
        try:
            teacher = Teacher.objects.get(id=attrs['teacher'])
        except Teacher.DoesNotExist:
            raise serializers.ValidationError({'teacher': '教师不存在'})
        try:
            semester = Semester.objects.get(id=attrs['semester'])
        except Semester.DoesNotExist:
            raise serializers.ValidationError({'semester': '学期不存在'})

        if not teacher.is_active:
            raise serializers.ValidationError({'teacher': '该教师已停用'})

        if not (semester.start_date <= attrs['date'] <= semester.end_date):
            raise serializers.ValidationError({
                'date': (
                    f'停排日期必须在学期范围内'
                    f'（{semester.start_date} ~ {semester.end_date}）'
                )
            })

        attrs['end_period'] = attrs['start_period'] + attrs['period_count'] - 1
        max_periods = (
            len(semester.daily_periods)
            if semester.daily_periods else 7
        )
        if attrs['end_period'] > max_periods:
            raise serializers.ValidationError({
                'period_count': (
                    f'每天只有 {max_periods} 节课，'
                    f'起始第 {attrs["start_period"]} 节连续 '
                    f'{attrs["period_count"]} 节超出范围'
                )
            })

        attrs['_teacher'] = teacher
        attrs['_semester'] = semester
        return attrs


class AutoScheduleRequestSerializer(serializers.Serializer):
    semester_id = serializers.IntegerField()
    respect_locked = serializers.BooleanField(default=True)


class ConflictCheckSerializer(serializers.Serializer):
    semester_id = serializers.IntegerField()


class SwapScheduleRequestSerializer(serializers.Serializer):
    entry1_id = serializers.IntegerField()
    entry2_id = serializers.IntegerField()
    reason = serializers.CharField(required=False, allow_blank=True)


class SubstituteRequestSerializer(serializers.Serializer):
    entry_id = serializers.IntegerField()
    substitute_teacher_id = serializers.IntegerField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    reason = serializers.CharField()
