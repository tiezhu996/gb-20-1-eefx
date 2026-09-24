"""手工调课（互换两节课）的校验逻辑。

互换前必须校验：
1. 两节课属于同一学期；
2. 锁定的课不允许直接互换（可通过 force 强制覆盖）；
3. 互换后的节次不能落在任课教师的临时停排时段（强制也不允许）；
4. 互换后不能产生新的教师 / 教室 / 班级时间冲突（可通过 force 强制覆盖）。
"""
from typing import Dict, List, Optional

from .models import ScheduleEntry, TeacherSuspension
from .suspension_utils import find_suspension_clashes


def _issue(code: str, severity: str, message: str, entry_id: Optional[int] = None) -> dict:
    return {
        'code': code,
        'severity': severity,  # 'error' 阻止操作 / 'warning' 可强制 / 'info' 仅提示
        'message': message,
        'entry_id': entry_id,
    }


def validate_swap(
    entry1: ScheduleEntry,
    entry2: ScheduleEntry,
    suspension_map: Dict[int, List[TeacherSuspension]]
) -> List[dict]:
    """校验互换两节课，返回问题列表；空列表表示可以直接互换。"""
    issues: List[dict] = []

    if entry1.semester_id != entry2.semester_id:
        issues.append(_issue(
            'different_semester', 'error',
            '两节课不属于同一学期，不能互换'
        ))
        return issues

    if entry1.day_of_week == entry2.day_of_week and entry1.period == entry2.period:
        issues.append(_issue('same_slot', 'info', '两节课本来就在同一时段，无需互换'))
        return issues

    # 锁定校验
    for entry in (entry1, entry2):
        if entry.is_locked:
            issues.append(_issue(
                'locked', 'warning',
                f'课程 {entry.course.name}（{entry.class_id.name}）已锁定，'
                f'互换会将其移动到周{entry2.day_of_week if entry == entry1 else entry1.day_of_week}'
                f'第{entry2.period if entry == entry1 else entry1.period}节',
                entry.id
            ))

    # 互换后各自的目标时段
    moves = [
        (entry1, entry2.day_of_week, entry2.period),
        (entry2, entry1.day_of_week, entry1.period),
    ]

    # 停排校验（硬约束，force 也不能覆盖）
    for entry, target_day, target_period in moves:
        clashes = find_suspension_clashes(
            entry.teacher_id, target_day, target_period, suspension_map
        )
        for suspension in clashes:
            issues.append(_issue(
                'suspension', 'error',
                f'教师 {entry.teacher.name} 在 {suspension.date.isoformat()} '
                f'第{suspension.start_period}-{suspension.end_period}节停排'
                f'（{suspension.reason}），无法把课换到周{target_day}第{target_period}节',
                entry.id
            ))

    # 互换后时间冲突校验（排除彼此，它们本来就分别占着目标时段）
    for entry, target_day, target_period in moves:
        occupants = ScheduleEntry.objects.filter(
            semester_id=entry.semester_id,
            day_of_week=target_day,
            period=target_period,
        ).exclude(id__in=[entry1.id, entry2.id]).select_related(
            'teacher', 'classroom', 'class_id', 'course'
        )
        for other in occupants:
            if other.teacher_id == entry.teacher_id:
                issues.append(_issue(
                    'teacher_conflict', 'warning',
                    f'教师 {entry.teacher.name} 在周{target_day}第{target_period}节'
                    f'已有课（{other.class_id.name} {other.course.name}）',
                    entry.id
                ))
            if other.classroom_id == entry.classroom_id:
                issues.append(_issue(
                    'classroom_conflict', 'warning',
                    f'教室 {entry.classroom.name} 在周{target_day}第{target_period}节'
                    f'已被 {other.class_id.name} {other.course.name} 占用',
                    entry.id
                ))
            if other.class_id_id == entry.class_id_id:
                issues.append(_issue(
                    'class_conflict', 'warning',
                    f'班级 {entry.class_id.name} 在周{target_day}第{target_period}节'
                    f'已有课（{other.course.name}）',
                    entry.id
                ))

    return issues


def is_blocking(issues: List[dict], force: bool = False) -> bool:
    """是否应阻止互换：error 始终阻止；warning 仅在 force 时放行。"""
    for issue in issues:
        if issue['severity'] == 'error':
            return True
        if issue['severity'] == 'warning' and not force:
            return True
    return False
