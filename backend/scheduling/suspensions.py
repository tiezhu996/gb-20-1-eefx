"""教师临时停排相关的规则工具。

课表按「周几-第几节」的周节奏安排，因此一条具体日期的停排登记
通过 `date.isoweekday()` 映射到课表中的 day_of_week 生效。
"""
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .models import TeacherSuspension, ScheduleEntry


def get_active_suspensions(semester) -> List[TeacherSuspension]:
    return list(
        TeacherSuspension.objects
        .filter(semester=semester, is_active=True)
        .select_related('teacher')
    )


def build_blocked_slots(
    suspensions: Iterable[TeacherSuspension]
) -> Dict[int, Set[Tuple[int, int]]]:
    """{teacher_id: {(day_of_week, period), ...}}"""
    blocked: Dict[int, Set[Tuple[int, int]]] = defaultdict(set)
    for s in suspensions:
        for period in range(s.start_period, s.end_period + 1):
            blocked[s.teacher_id].add((s.day_of_week, period))
    return blocked


def find_suspension_for_slot(
    suspensions: Iterable[TeacherSuspension],
    teacher_id: int,
    day_of_week: int,
    period: int,
) -> Optional[TeacherSuspension]:
    """返回某教师在某周几某节命中的第一条生效停排（没有则 None）"""
    for s in suspensions:
        if (s.teacher_id == teacher_id
                and s.covers_slot(day_of_week, period)):
            return s
    return None


def find_locked_suspension_conflicts(
    semester,
    suspensions: Optional[Iterable[TeacherSuspension]] = None,
) -> List[Dict]:
    """此前已锁定、且恰好落在停排时段内的课。

    锁定课重新排课时留在原处不移动，命中停排时单独标出，
    方便教务继续人工调整。
    """
    if suspensions is None:
        suspensions = get_active_suspensions(semester)
    suspensions = list(suspensions)

    locked_entries = (
        ScheduleEntry.objects
        .filter(semester=semester, is_locked=True)
        .select_related('teacher', 'course', 'class_id', 'classroom')
    )

    conflicts = []
    for entry in locked_entries:
        suspension = find_suspension_for_slot(
            suspensions, entry.teacher_id,
            entry.day_of_week, entry.period
        )
        if suspension:
            conflicts.append({
                'entry_id': entry.id,
                'teacher_id': entry.teacher_id,
                'teacher_name': entry.teacher.name,
                'class_id': entry.class_id_id,
                'class_name': entry.class_id.name,
                'course_name': entry.course.name,
                'day_of_week': entry.day_of_week,
                'period': entry.period,
                'suspension_id': suspension.id,
                'suspension_date': suspension.date.isoformat(),
                'suspension_reason': suspension.reason,
                'message': (
                    f"已锁定课程「{entry.course.name}」（{entry.teacher.name}）"
                    f"位于周{entry.day_of_week}第{entry.period}节，"
                    f"与 {suspension.date} 的停排登记"
                    f"（{suspension.reason}）冲突，课程仍保留在原处"
                ),
            })
    return conflicts


def find_suspension_for_entry(
    suspensions: Iterable[TeacherSuspension],
    entry: ScheduleEntry,
) -> Optional[TeacherSuspension]:
    """一节课（按实际任课教师）是否落在停排时段内"""
    return find_suspension_for_slot(
        suspensions, entry.teacher_id, entry.day_of_week, entry.period
    )


def validate_swap(
    entry1: ScheduleEntry,
    entry2: ScheduleEntry,
    suspensions: Iterable[TeacherSuspension],
) -> List[str]:
    """手工互换两节课前的校验，返回错误信息列表（为空表示通过）。"""
    errors: List[str] = []
    suspensions = list(suspensions)

    if entry1.semester_id != entry2.semester_id:
        errors.append('两节课不属于同一学期，不能互换')
        return errors

    if entry1.is_locked or entry2.is_locked:
        locked_names = []
        if entry1.is_locked:
            locked_names.append(f"周{entry1.day_of_week}第{entry1.period}节")
        if entry2.is_locked:
            locked_names.append(f"周{entry2.day_of_week}第{entry2.period}节")
        errors.append(
            f"锁定的课程不能互换（{'、'.join(locked_names)}），请先解锁"
        )

    # 互换后 entry1 的教师到 entry2 的时段，entry2 的教师到 entry1 的时段
    target_s2 = find_suspension_for_slot(
        suspensions, entry1.teacher_id, entry2.day_of_week, entry2.period
    )
    if target_s2:
        errors.append(
            f"教师 {entry1.teacher.name} 在 {target_s2.date}"
            f"（周{target_s2.day_of_week}第{entry2.period}节）已登记停排"
            f"（{target_s2.reason}），不能换到此时段"
        )

    target_s1 = find_suspension_for_slot(
        suspensions, entry2.teacher_id, entry1.day_of_week, entry1.period
    )
    if target_s1:
        errors.append(
            f"教师 {entry2.teacher.name} 在 {target_s1.date}"
            f"（周{target_s1.day_of_week}第{entry1.period}节）已登记停排"
            f"（{target_s1.reason}），不能换到此时段"
        )

    return errors
