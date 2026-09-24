from rest_framework import serializers
from .models import (
    ClassCourse, ScheduleEntry, Conflict, SwapRequest, Substitute,
    TeacherSuspension
)
from .suspension_utils import (
    active_suspensions_for_semester,
    suspensions_by_teacher,
    flags_for_entry,
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
    suspension_flags = serializers.SerializerMethodField()

    class Meta:
        model = ScheduleEntry
        fields = '__all__'

    def get_suspension_flags(self, obj):
        """命中的有效停排（视图在 context['suspension_map'] 中按学期预取）。"""
        suspension_map = self.context.get('suspension_map')
        if suspension_map is None:
            suspension_map = suspensions_by_teacher(
                active_suspensions_for_semester(obj.semester)
            )
        return flags_for_entry(obj, suspension_map)


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
    end_period = serializers.IntegerField(read_only=True)
    day_of_week = serializers.IntegerField(read_only=True)

    class Meta:
        model = TeacherSuspension
        fields = '__all__'

    def validate(self, attrs):
        teacher = attrs.get('teacher') or getattr(self.instance, 'teacher', None)
        date_val = attrs.get('date') or getattr(self.instance, 'date', None)
        start_period = attrs.get('start_period', getattr(self.instance, 'start_period', 1))
        period_count = attrs.get('period_count', getattr(self.instance, 'period_count', 1))

        if start_period < 1:
            raise serializers.ValidationError({'start_period': '起始节次必须大于 0'})
        if period_count < 1:
            raise serializers.ValidationError({'period_count': '连续节数必须大于 0'})

        if teacher and date_val:
            new_end = start_period + period_count - 1
            queryset = TeacherSuspension.objects.filter(
                teacher=teacher, date=date_val, is_active=True
            )
            if self.instance:
                queryset = queryset.exclude(id=self.instance.id)
            for existing in queryset:
                if start_period <= existing.end_period and existing.start_period <= new_end:
                    raise serializers.ValidationError(
                        {'non_field_errors': [
                            f'与该教师 {date_val} 已有的停排（第'
                            f'{existing.start_period}-{existing.end_period}节）时间重叠'
                        ]}
                    )
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
    force = serializers.BooleanField(
        default=False, help_text='强制覆盖锁定 / 冲突类警告（停排冲突不可覆盖）'
    )


class SwapValidateRequestSerializer(serializers.Serializer):
    entry1_id = serializers.IntegerField()
    entry2_id = serializers.IntegerField()


class SubstituteRequestSerializer(serializers.Serializer):
    entry_id = serializers.IntegerField()
    substitute_teacher_id = serializers.IntegerField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    reason = serializers.CharField()
