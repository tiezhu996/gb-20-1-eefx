from django.db import models
from django.utils import timezone
from core.models import Classroom, Teacher, Class, Course, Semester


class ClassCourse(models.Model):
    class_id = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='course_assignments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['class_id', 'course', 'teacher', 'semester']
        ordering = ['semester', 'class_id']

    def __str__(self):
        return f"{self.class_id} - {self.course} ({self.teacher})"


class ScheduleEntry(models.Model):
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    class_id = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='schedules')
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE)
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE)
    day_of_week = models.IntegerField(help_text='1-5 代表周一到周五')
    period = models.IntegerField(help_text='第几节课')
    is_locked = models.BooleanField(default=False, help_text='锁定后不参与自动重排')
    is_conflict = models.BooleanField(default=False)
    conflict_type = models.CharField(max_length=50, blank=True)
    original_teacher = models.ForeignKey(
        Teacher, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='substitute_for',
        help_text='如果是代课，记录原教师'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['semester', 'day_of_week', 'period']

    def __str__(self):
        return (f"{self.class_id} - {self.course} @ "
                f"周{self.day_of_week}第{self.period}节")


class TeacherSuspension(models.Model):
    """教师临时停排：教师在某个具体日期的连续几节课不参与排课"""

    teacher = models.ForeignKey(
        Teacher, on_delete=models.CASCADE,
        related_name='suspensions', help_text='停排教师'
    )
    date = models.DateField(help_text='停排具体日期')
    start_period = models.PositiveIntegerField(default=1, help_text='从第几节开始')
    period_count = models.PositiveIntegerField(default=1, help_text='连续停排的节数')
    reason = models.CharField(max_length=200, help_text='停排原因，如请假、校外培训')
    is_active = models.BooleanField(default=True, help_text='取消后置为 False')
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return (f"{self.teacher.name} 停排 {self.date} "
                f"第{self.start_period}-{self.end_period}节")

    @property
    def end_period(self) -> int:
        return self.start_period + self.period_count - 1

    @property
    def day_of_week(self) -> int:
        """Python isoweekday：1=周一 ... 7=周日，与 ScheduleEntry.day_of_week 一致"""
        return self.date.isoweekday()

    def covers(self, day_of_week: int, period: int) -> bool:
        return (
            self.day_of_week == day_of_week
            and self.start_period <= period <= self.end_period
        )

    def cancel(self):
        """取消停排（保留记录供追溯），后续排课不再避开此时段。"""
        self.is_active = False
        self.cancelled_at = timezone.now()
        self.save(update_fields=['is_active', 'cancelled_at', 'updated_at'])


class Conflict(models.Model):
    CONFLICT_TYPES = [
        ('teacher', '教师冲突'),
        ('classroom', '教室冲突'),
        ('class', '班级冲突'),
        ('suspension', '停排冲突'),
    ]

    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    conflict_type = models.CharField(max_length=20, choices=CONFLICT_TYPES)
    day_of_week = models.IntegerField()
    period = models.IntegerField()
    involved_entries = models.JSONField(default=list)
    message = models.TextField()
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_conflict_type_display()} @ 周{self.day_of_week}第{self.period}节"


class SwapRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', '待审批'),
        ('approved', '已批准'),
        ('rejected', '已拒绝'),
    ]

    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    requesting_teacher = models.ForeignKey(
        Teacher, on_delete=models.CASCADE, related_name='swap_requests_made'
    )
    target_teacher = models.ForeignKey(
        Teacher, on_delete=models.CASCADE, related_name='swap_requests_received'
    )
    entry1 = models.ForeignKey(
        ScheduleEntry, on_delete=models.CASCADE, related_name='swap_source'
    )
    entry2 = models.ForeignKey(
        ScheduleEntry, on_delete=models.CASCADE, related_name='swap_target'
    )
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"调课申请: {self.requesting_teacher} <-> {self.target_teacher}"


class Substitute(models.Model):
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    original_teacher = models.ForeignKey(
        Teacher, on_delete=models.CASCADE, related_name='absences'
    )
    substitute_teacher = models.ForeignKey(
        Teacher, on_delete=models.CASCADE, related_name='substitutions'
    )
    affected_entry = models.ForeignKey(
        ScheduleEntry, on_delete=models.CASCADE, related_name='substitute_record'
    )
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.substitute_teacher} 代 {self.original_teacher}"
