from django.http import HttpResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.db import transaction
from core.models import Semester, Classroom, Teacher, Class
from .models import (
    ClassCourse, ScheduleEntry, Conflict, SwapRequest, Substitute,
    TeacherSuspension
)
from .serializers import (
    ClassCourseSerializer, ScheduleEntrySerializer,
    ScheduleEntryDetailSerializer, ConflictSerializer,
    SwapRequestSerializer, SubstituteSerializer,
    TeacherSuspensionSerializer,
    AutoScheduleRequestSerializer, ConflictCheckSerializer,
    SwapScheduleRequestSerializer, SwapValidateRequestSerializer,
    SubstituteRequestSerializer
)
from .csp_solver import CSPScheduler, ConflictDetector, SchedulingTask, TimeSlot
from .manual_adjust import validate_swap, is_blocking
from .suspension_utils import (
    active_suspensions_for_semester,
    suspensions_by_teacher,
    blocked_teacher_slots,
    flags_for_entry,
)
from .pdf_export import (
    generate_class_timetable_pdf,
    generate_teacher_timetable_pdf,
    generate_classroom_timetable_pdf
)


class ClassCourseViewSet(viewsets.ModelViewSet):
    queryset = ClassCourse.objects.all()
    serializer_class = ClassCourseSerializer
    permission_classes = [AllowAny]


class ScheduleEntryViewSet(viewsets.ModelViewSet):
    queryset = ScheduleEntry.objects.all().select_related(
        'course', 'teacher', 'classroom', 'class_id', 'semester'
    )
    serializer_class = ScheduleEntryDetailSerializer
    permission_classes = [AllowAny]

    def get_serializer_context(self):
        """按查询参数中的学期预取停排，供 suspension_flags 标记使用。"""
        context = super().get_serializer_context()
        semester_id = self.request.query_params.get('semester_id')
        if semester_id:
            try:
                semester = Semester.objects.get(id=semester_id)
            except Semester.DoesNotExist:
                semester = None
            if semester:
                context['suspension_map'] = suspensions_by_teacher(
                    active_suspensions_for_semester(semester)
                )
        return context

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return ScheduleEntryDetailSerializer
        return ScheduleEntrySerializer

    @action(detail=False, methods=['get'])
    def by_semester(self, request):
        semester_id = request.query_params.get('semester_id')
        if not semester_id:
            return Response(
                {'error': 'semester_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        entries = self.queryset.filter(semester_id=semester_id)
        serializer = ScheduleEntryDetailSerializer(
            entries, many=True, context=self.get_serializer_context()
        )
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_class(self, request):
        semester_id = request.query_params.get('semester_id')
        class_id = request.query_params.get('class_id')
        entries = self.queryset.filter(semester_id=semester_id, class_id=class_id)
        serializer = ScheduleEntryDetailSerializer(
            entries, many=True, context=self.get_serializer_context()
        )
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_teacher(self, request):
        semester_id = request.query_params.get('semester_id')
        teacher_id = request.query_params.get('teacher_id')
        entries = self.queryset.filter(semester_id=semester_id, teacher_id=teacher_id)
        serializer = ScheduleEntryDetailSerializer(
            entries, many=True, context=self.get_serializer_context()
        )
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_classroom(self, request):
        semester_id = request.query_params.get('semester_id')
        classroom_id = request.query_params.get('classroom_id')
        entries = self.queryset.filter(semester_id=semester_id, classroom_id=classroom_id)
        serializer = ScheduleEntryDetailSerializer(
            entries, many=True, context=self.get_serializer_context()
        )
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def auto_schedule(self, request):
        req_serializer = AutoScheduleRequestSerializer(data=request.data)
        if not req_serializer.is_valid():
            return Response(req_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        semester_id = req_serializer.validated_data['semester_id']
        respect_locked = req_serializer.validated_data['respect_locked']

        try:
            semester = Semester.objects.get(id=semester_id)
        except Semester.DoesNotExist:
            return Response(
                {'error': 'Semester not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        class_courses = ClassCourse.objects.filter(
            semester=semester
        ).select_related('class_id', 'course', 'teacher')

        if not class_courses.exists():
            return Response(
                {'error': 'No class courses configured for this semester'},
                status=status.HTTP_400_BAD_REQUEST
            )

        tasks = []
        for cc in class_courses:
            tasks.append(SchedulingTask(
                class_id=cc.class_id.id,
                course_id=cc.course.id,
                teacher_id=cc.teacher.id,
                weekly_hours=cc.course.weekly_hours,
                preferred_room_type=cc.course.preferred_room_type,
                priority=cc.course.priority,
                available_time_slots=[],
                classroom_capacity=cc.class_id.student_count or 40
            ))

        classrooms_data = {
            c.id: {
                'room_type': c.room_type,
                'capacity': c.capacity,
                'name': c.name
            } for c in Classroom.objects.filter(is_active=True)
        }

        teachers_data = {
            t.id: {
                'name': t.name,
                'available_time_slots': t.available_time_slots if t.available_time_slots else []
            } for t in Teacher.objects.filter(is_active=True)
        }

        locked_entries = []
        if respect_locked:
            locked = ScheduleEntry.objects.filter(
                semester=semester, is_locked=True
            ).values(
                'id', 'class_id', 'teacher_id', 'classroom_id',
                'day_of_week', 'period', 'is_locked'
            )
            locked_entries = list(locked)

        # 学期内有效的教师临时停排：自动排课必须避开这些时段
        suspensions = active_suspensions_for_semester(semester)
        suspension_map = suspensions_by_teacher(suspensions)
        teacher_blocked_slots = blocked_teacher_slots(suspensions)

        scheduler = CSPScheduler(semester)
        assignments, scheduling_conflicts = scheduler.schedule(
            tasks, classrooms_data, teachers_data, locked_entries,
            blocked_teacher_slots=teacher_blocked_slots
        )

        with transaction.atomic():
            if respect_locked:
                ScheduleEntry.objects.filter(
                    semester=semester, is_locked=False
                ).delete()
            else:
                ScheduleEntry.objects.filter(semester=semester).delete()

            bulk_entries = []
            for a in assignments:
                if a.get('is_locked'):
                    continue
                bulk_entries.append(ScheduleEntry(
                    semester_id=a['semester_id'],
                    class_id_id=a['class_id'],
                    course_id=a['course_id'],
                    teacher_id=a['teacher_id'],
                    classroom_id=a['classroom_id'],
                    day_of_week=a['day_of_week'],
                    period=a['period'],
                    is_locked=False
                ))
            ScheduleEntry.objects.bulk_create(bulk_entries)

            # 重排后重置历史冲突标记（锁定的课被保留，其标记可能已过时）
            ScheduleEntry.objects.filter(semester=semester).update(
                is_conflict=False, conflict_type=''
            )

            all_entries_qs = ScheduleEntry.objects.filter(
                semester=semester
            ).values('id', 'teacher_id', 'classroom_id', 'class_id',
                     'day_of_week', 'period', 'is_locked')
            all_entries = list(all_entries_qs)

            # 锁定课恰好落在停排时段：保留原处并走单独的停排警告，
            # 不参与常规红绿冲突标注（新排的课已被 CSP 避开该教师，不会与之冲突）
            locked_suspended_ids = set()
            if respect_locked:
                for entry in all_entries:
                    if not entry['is_locked']:
                        continue
                    for suspension in suspension_map.get(entry['teacher_id'], []):
                        if suspension.covers(entry['day_of_week'], entry['period']):
                            locked_suspended_ids.add(entry['id'])
                            break

            detector = ConflictDetector()
            conflicts = [
                c for c in detector.detect_conflicts(all_entries)
                if not set(c['involved_entries']).issubset(locked_suspended_ids)
            ]

            Conflict.objects.filter(semester=semester).delete()
            bulk_conflicts = []
            for c in conflicts:
                bulk_conflicts.append(Conflict(
                    semester=semester,
                    conflict_type=c['conflict_type'],
                    day_of_week=c['day_of_week'],
                    period=c['period'],
                    involved_entries=c['involved_entries'],
                    message=c['message']
                ))
            Conflict.objects.bulk_create(bulk_conflicts)

            for c in conflicts:
                ids = [
                    eid for eid in c['involved_entries']
                    if eid not in locked_suspended_ids
                ]
                if ids:
                    ScheduleEntry.objects.filter(id__in=ids).update(
                        is_conflict=True, conflict_type=c['conflict_type']
                    )

        final_entries = ScheduleEntry.objects.filter(
            semester=semester
        ).select_related('course', 'teacher', 'classroom', 'class_id')
        serializer = ScheduleEntryDetailSerializer(
            final_entries, many=True,
            context={'suspension_map': suspension_map}
        )

        # 此前已锁定的课不参与重排，若恰好落在教师停排时段，单独标出
        locked_suspension_warnings = []
        if respect_locked:
            for entry in final_entries.filter(is_locked=True):
                flags = flags_for_entry(entry, suspension_map)
                for flag in flags:
                    locked_suspension_warnings.append({
                        'entry_id': entry.id,
                        'teacher_id': entry.teacher_id,
                        'teacher_name': entry.teacher.name,
                        'class_name': entry.class_id.name,
                        'course_name': entry.course.name,
                        'day_of_week': entry.day_of_week,
                        'period': entry.period,
                        'is_locked': True,
                        **flag,
                    })

        return Response({
            'schedule': serializer.data,
            'conflicts': conflicts,
            'scheduling_messages': scheduling_conflicts,
            'locked_suspension_warnings': locked_suspension_warnings,
            'total_entries': len(serializer.data)
        })

    @action(detail=False, methods=['post'])
    def check_conflicts(self, request):
        req_serializer = ConflictCheckSerializer(data=request.data)
        if not req_serializer.is_valid():
            return Response(req_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        semester_id = req_serializer.validated_data['semester_id']
        entries = ScheduleEntry.objects.filter(
            semester_id=semester_id
        ).values('id', 'teacher_id', 'classroom_id', 'class_id', 'day_of_week', 'period')

        detector = ConflictDetector()
        conflicts = detector.detect_conflicts(list(entries))

        return Response({'conflicts': conflicts})

    @action(detail=False, methods=['post'], url_path='swap/validate')
    def validate_swap(self, request):
        """只校验不执行，返回互换后可能出现的全部问题（停排/锁定/冲突）。"""
        req_serializer = SwapValidateRequestSerializer(data=request.data)
        if not req_serializer.is_valid():
            return Response(req_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            entry1 = ScheduleEntry.objects.select_related(
                'teacher', 'classroom', 'class_id', 'course', 'semester'
            ).get(id=req_serializer.validated_data['entry1_id'])
            entry2 = ScheduleEntry.objects.select_related(
                'teacher', 'classroom', 'class_id', 'course', 'semester'
            ).get(id=req_serializer.validated_data['entry2_id'])
        except ScheduleEntry.DoesNotExist:
            return Response(
                {'error': 'One or both entries not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        semester = entry1.semester
        suspension_map = suspensions_by_teacher(
            active_suspensions_for_semester(semester)
        )
        issues = validate_swap(entry1, entry2, suspension_map)
        return Response({
            'valid': not is_blocking(issues, force=False),
            'forceable': not is_blocking(issues, force=True),
            'issues': issues
        })

    @action(detail=False, methods=['post'])
    def swap(self, request):
        req_serializer = SwapScheduleRequestSerializer(data=request.data)
        if not req_serializer.is_valid():
            return Response(req_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        entry1_id = req_serializer.validated_data['entry1_id']
        entry2_id = req_serializer.validated_data['entry2_id']
        reason = req_serializer.validated_data.get('reason', '')
        force = req_serializer.validated_data.get('force', False)

        try:
            entry1 = ScheduleEntry.objects.select_related(
                'teacher', 'classroom', 'class_id', 'course', 'semester'
            ).get(id=entry1_id)
            entry2 = ScheduleEntry.objects.select_related(
                'teacher', 'classroom', 'class_id', 'course', 'semester'
            ).get(id=entry2_id)
        except ScheduleEntry.DoesNotExist:
            return Response(
                {'error': 'One or both entries not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        suspension_map = suspensions_by_teacher(
            active_suspensions_for_semester(entry1.semester)
        )
        issues = validate_swap(entry1, entry2, suspension_map)
        if is_blocking(issues, force=force):
            return Response({
                'error': 'Swap validation failed',
                'issues': issues,
                'forceable': not is_blocking(issues, force=True)
            }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            day1, period1 = entry1.day_of_week, entry1.period
            day2, period2 = entry2.day_of_week, entry2.period

            entry1.day_of_week, entry1.period = day2, period2
            entry2.day_of_week, entry2.period = day1, period1

            entry1.save()
            entry2.save()

            if reason:
                SwapRequest.objects.create(
                    semester=entry1.semester,
                    requesting_teacher=entry1.teacher,
                    target_teacher=entry2.teacher,
                    entry1=entry1,
                    entry2=entry2,
                    reason=reason,
                    status='approved'
                )

        warnings = [i for i in issues if i['severity'] == 'warning']
        return Response({
            'status': 'success',
            'message': 'Swap completed',
            'forced': force and bool(warnings),
            'warnings': warnings
        })

    @action(detail=False, methods=['post'])
    def substitute(self, request):
        req_serializer = SubstituteRequestSerializer(data=request.data)
        if not req_serializer.is_valid():
            return Response(req_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        entry_id = req_serializer.validated_data['entry_id']
        substitute_teacher_id = req_serializer.validated_data['substitute_teacher_id']
        start_date = req_serializer.validated_data['start_date']
        end_date = req_serializer.validated_data['end_date']
        reason = req_serializer.validated_data['reason']

        try:
            entry = ScheduleEntry.objects.get(id=entry_id)
            substitute_teacher = Teacher.objects.get(id=substitute_teacher_id)
        except (ScheduleEntry.DoesNotExist, Teacher.DoesNotExist):
            return Response(
                {'error': 'Entry or teacher not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        original_teacher = entry.teacher

        with transaction.atomic():
            Substitute.objects.create(
                semester=entry.semester,
                original_teacher=original_teacher,
                substitute_teacher=substitute_teacher,
                affected_entry=entry,
                start_date=start_date,
                end_date=end_date,
                reason=reason
            )

            entry.original_teacher = original_teacher
            entry.teacher = substitute_teacher
            entry.save()

        serializer = ScheduleEntryDetailSerializer(entry)
        return Response({'status': 'success', 'entry': serializer.data})

    @action(detail=False, methods=['get'])
    def export_pdf(self, request):
        semester_id = request.query_params.get('semester_id')
        entity_type = request.query_params.get('type')
        entity_id = request.query_params.get('id')

        try:
            semester = Semester.objects.get(id=semester_id)
        except Semester.DoesNotExist:
            return Response(
                {'error': 'Semester not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        pdf_buffer = None
        filename = 'timetable.pdf'

        try:
            if entity_type == 'class':
                class_obj = Class.objects.get(id=entity_id)
                pdf_buffer = generate_class_timetable_pdf(class_obj, semester)
                filename = f'{class_obj.name}_课表.pdf'
            elif entity_type == 'teacher':
                teacher = Teacher.objects.get(id=entity_id)
                pdf_buffer = generate_teacher_timetable_pdf(teacher, semester)
                filename = f'{teacher.name}_课表.pdf'
            elif entity_type == 'classroom':
                classroom = Classroom.objects.get(id=entity_id)
                pdf_buffer = generate_classroom_timetable_pdf(classroom, semester)
                filename = f'{classroom.name}_课表.pdf'
            else:
                return Response(
                    {'error': 'Invalid type. Must be class, teacher, or classroom'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except (Class.DoesNotExist, Teacher.DoesNotExist, Classroom.DoesNotExist):
            return Response(
                {'error': 'Entity not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        response = HttpResponse(pdf_buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class ConflictViewSet(viewsets.ModelViewSet):
    queryset = Conflict.objects.all().select_related('semester')
    serializer_class = ConflictSerializer
    permission_classes = [AllowAny]


class SwapRequestViewSet(viewsets.ModelViewSet):
    queryset = SwapRequest.objects.all().select_related(
        'semester', 'requesting_teacher', 'target_teacher'
    )
    serializer_class = SwapRequestSerializer
    permission_classes = [AllowAny]


class SubstituteViewSet(viewsets.ModelViewSet):
    queryset = Substitute.objects.all().select_related(
        'semester', 'original_teacher', 'substitute_teacher'
    )
    serializer_class = SubstituteSerializer
    permission_classes = [AllowAny]


class TeacherSuspensionViewSet(viewsets.ModelViewSet):
    """教师临时停排登记。支持按教师 / 日期 / 有效状态筛选，以及后续取消。"""

    queryset = TeacherSuspension.objects.all().select_related('teacher')
    serializer_class = TeacherSuspensionSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = super().get_queryset()
        teacher_id = self.request.query_params.get('teacher_id')
        date_val = self.request.query_params.get('date')
        is_active = self.request.query_params.get('is_active')

        if teacher_id:
            queryset = queryset.filter(teacher_id=teacher_id)
        if date_val:
            queryset = queryset.filter(date=date_val)
        if is_active is not None and is_active != '':
            queryset = queryset.filter(is_active=is_active.lower() in ('true', '1'))
        return queryset

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        suspension = self.get_object()
        if not suspension.is_active:
            return Response(
                {'status': 'already_cancelled',
                 'message': '该停排已取消'},
                status=status.HTTP_400_BAD_REQUEST
            )
        suspension.cancel()
        serializer = self.get_serializer(suspension)
        return Response({'status': 'success', 'suspension': serializer.data})
