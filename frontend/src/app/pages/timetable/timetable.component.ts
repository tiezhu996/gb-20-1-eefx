import { Component, OnInit, ViewChild, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatCardModule } from '@angular/material/card';
import { MatTableModule } from '@angular/material/table';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import { HttpErrorResponse } from '@angular/common/http';
import { FullCalendarModule } from '@fullcalendar/angular';
import { CalendarOptions } from '@fullcalendar/core';
import dayGridPlugin from '@fullcalendar/daygrid';
import timeGridPlugin from '@fullcalendar/timegrid';
import interactionPlugin from '@fullcalendar/interaction';
import { ApiService } from '../../services/api.service';
import type {
  ScheduleEntry, Semester, Class, Teacher, Classroom,
  SwapIssue, LockedSuspensionWarning
} from '../../types';

@Component({
  selector: 'app-timetable',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatFormFieldModule,
    MatSelectModule,
    MatButtonModule,
    MatCheckboxModule,
    MatCardModule,
    MatTableModule,
    MatIconModule,
    MatChipsModule,
    FullCalendarModule
  ],
  template: `
    <div class="page-container">
      <h1 class="page-title">课表管理</h1>

      <div class="filter-bar">
        <mat-form-field class="filter-select">
          <mat-label>学期</mat-label>
          <mat-select [(value)]="selectedSemesterId" (selectionChange)="onSemesterChange()">
            <mat-option *ngFor="let s of semesters" [value]="s.id">
              {{ s.name }}
              <span *ngIf="s.is_active" style="color: green;"> (当前)</span>
            </mat-option>
          </mat-select>
        </mat-form-field>

        <mat-form-field class="filter-select">
          <mat-label>查看方式</mat-label>
          <mat-select [(value)]="viewMode" (selectionChange)="loadSchedules()">
            <mat-option value="class">按班级</mat-option>
            <mat-option value="teacher">按教师</mat-option>
            <mat-option value="classroom">按教室</mat-option>
          </mat-select>
        </mat-form-field>

        <mat-form-field class="filter-select" *ngIf="viewMode === 'class'">
          <mat-label>班级</mat-label>
          <mat-select [(value)]="selectedClassId" (selectionChange)="loadSchedules()">
            <mat-option *ngFor="let c of classes" [value]="c.id">
              {{ c.grade }}年级 {{ c.name }}
            </mat-option>
          </mat-select>
        </mat-form-field>

        <mat-form-field class="filter-select" *ngIf="viewMode === 'teacher'">
          <mat-label>教师</mat-label>
          <mat-select [(value)]="selectedTeacherId" (selectionChange)="loadSchedules()">
            <mat-option *ngFor="let t of teachers" [value]="t.id">
              {{ t.name }}
            </mat-option>
          </mat-select>
        </mat-form-field>

        <mat-form-field class="filter-select" *ngIf="viewMode === 'classroom'">
          <mat-label>教室</mat-label>
          <mat-select [(value)]="selectedClassroomId" (selectionChange)="loadSchedules()">
            <mat-option *ngFor="let c of classrooms" [value]="c.id">
              {{ c.name }}
            </mat-option>
          </mat-select>
        </mat-form-field>
      </div>

      <div class="action-bar">
        <button mat-raised-button color="primary" (click)="runAutoSchedule(true)" [disabled]="!selectedSemesterId">
          <mat-icon>auto_awesome</mat-icon>
          自动排课（保留锁定）
        </button>
        <button mat-raised-button (click)="runAutoSchedule(false)" [disabled]="!selectedSemesterId">
          <mat-icon>refresh</mat-icon>
          重新排课（忽略锁定）
        </button>
        <button mat-button (click)="loadSchedules()">
          <mat-icon>refresh</mat-icon>
          刷新
        </button>
        <button mat-raised-button color="accent" (click)="exportPdf()" [disabled]="!canExport">
          <mat-icon>picture_as_pdf</mat-icon>
          导出 PDF
        </button>
        <button mat-raised-button (click)="exportImage()" [disabled]="!canExport">
          <mat-icon>image</mat-icon>
          导出图片
        </button>
      </div>

      <mat-card class="swap-hint">
        <mat-card-content>
          <mat-icon>swap_horiz</mat-icon>
          <span>
            手工互换：先点选一节课（蓝色描边），再点另一节课完成互换；
            系统会先校验锁定、停排和时间冲突。
          </span>
          <button *ngIf="selectedSwapEntry" mat-button color="warn" (click)="clearSwapSelection()">
            <mat-icon>close</mat-icon> 取消选择
          </button>
        </mat-card-content>
      </mat-card>

      <div *ngIf="schedulingMessage" style="margin-top: 12px;">
        <mat-card>
          <mat-card-content>
            <p [innerHTML]="schedulingMessage"></p>
          </mat-card-content>
        </mat-card>
      </div>

      <!-- 锁定课碰到停排：单独标出，方便教务继续调整 -->
      <div *ngIf="lockedWarnings.length > 0" class="warning-panel">
        <h4>
          <mat-icon>warning</mat-icon>
          以下已锁定的课仍在原处，但任课教师该时段有临时停排，请继续调整：
        </h4>
        <ul>
          <li *ngFor="let w of lockedWarnings">
            {{ w.teacher_name }} 的 {{ w.course_name }}（{{ w.class_name }}）
            在周{{ w.day_of_week }}第{{ w.period }}节，
            命中 {{ w.date }} 第{{ w.start_period }}-{{ w.end_period }}节停排（{{ w.reason }}）
          </li>
        </ul>
        <button mat-stroked-button (click)="lockedWarnings = []">知道了</button>
      </div>

      <div class="timetable-container" #timetableContainer>
        <div *ngIf="schedules.length > 0">
          <h3 style="padding: 16px 16px 0; margin: 0;">{{ currentViewTitle }}</h3>

          <div style="padding: 16px; overflow-x: auto;">
            <table class="mat-elevation-z2" style="width: 100%; border-collapse: collapse;">
              <thead>
                <tr style="background: #1976d2; color: white;">
                  <th style="padding: 12px; text-align: center; min-width: 100px;">节次</th>
                  <th *ngFor="let day of weekDays" style="padding: 12px; text-align: center; min-width: 150px;">
                    {{ day }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr *ngFor="let period of periods; let i = index" [style.background]="i % 2 === 0 ? '#f9f9f9' : 'white'">
                  <td style="padding: 12px; text-align: center; font-weight: bold; border: 1px solid #ddd;">
                    {{ period.name }}
                  </td>
                  <td
                    *ngFor="let day of weekDayNumbers; let di = index"
                    style="padding: 8px; border: 1px solid #ddd; vertical-align: top; min-height: 80px;"
                  >
                    <ng-container *ngFor="let entry of getEntryAt(day, i + 1)">
                      <mat-card
                        class="schedule-card"
                        [class.conflict-entry]="entry.is_conflict"
                        [class.locked-entry]="entry.is_locked"
                        [class.suspension-entry]="hasSuspensionFlag(entry)"
                        [class.swap-selected]="selectedSwapEntry?.id === entry.id"
                        style="margin-bottom: 4px; cursor: pointer;"
                        (click)="onEntryClick(entry)"
                      >
                        <div class="schedule-course">{{ entry.course_name }}</div>
                        <div class="schedule-detail">{{ entry.teacher_name }}</div>
                        <div class="schedule-detail">{{ entry.classroom_name }}</div>
                        <div class="schedule-detail">{{ entry.class_name }}</div>
                        <div style="margin-top: 4px; display: flex; gap: 4px; flex-wrap: wrap;">
                          <mat-chip *ngIf="entry.is_locked" color="accent" selected>锁定</mat-chip>
                          <mat-chip *ngIf="entry.is_conflict" color="warn" selected>冲突</mat-chip>
                          <mat-chip *ngIf="hasSuspensionFlag(entry)" class="suspension-chip" selected>
                            停排
                          </mat-chip>
                          <button
                            mat-icon-button
                            size="small"
                            (click)="toggleLock(entry); $event.stopPropagation()"
                            [title]="entry.is_locked ? '解锁' : '锁定'"
                          >
                            <mat-icon>{{ entry.is_locked ? 'lock' : 'lock_open' }}</mat-icon>
                          </button>
                        </div>
                      </mat-card>
                    </ng-container>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div *ngIf="schedules.length === 0 && selectedSemesterId" style="padding: 40px; text-align: center;">
          <p>当前没有排课数据。点击"自动排课"按钮开始。</p>
        </div>

        <div *ngIf="!selectedSemesterId" style="padding: 40px; text-align: center;">
          <p>请先选择一个学期。</p>
        </div>
      </div>
    </div>
  `
})
export class TimetableComponent implements OnInit {
  @ViewChild('timetableContainer') timetableContainer!: ElementRef;

  semesters: Semester[] = [];
  classes: Class[] = [];
  teachers: Teacher[] = [];
  classrooms: Classroom[] = [];
  schedules: ScheduleEntry[] = [];
  selectedSemesterId: number | null = null;
  selectedClassId: number | null = null;
  selectedTeacherId: number | null = null;
  selectedClassroomId: number | null = null;
  viewMode: 'class' | 'teacher' | 'classroom' = 'class';
  schedulingMessage: string = '';
  currentSemester: Semester | null = null;
  selectedSwapEntry: ScheduleEntry | null = null;
  lockedWarnings: LockedSuspensionWarning[] = [];

  weekDays = ['星期一', '星期二', '星期三', '星期四', '星期五'];
  weekDayNumbers = [1, 2, 3, 4, 5];
  periods = [
    { name: '第1节', order: 1 },
    { name: '第2节', order: 2 },
    { name: '第3节', order: 3 },
    { name: '第4节', order: 4 },
    { name: '第5节', order: 5 },
    { name: '第6节', order: 6 },
    { name: '第7节', order: 7 },
  ];

  calendarOptions: CalendarOptions = {
    plugins: [dayGridPlugin, timeGridPlugin, interactionPlugin]
  };

  get canExport(): boolean {
    if (!this.selectedSemesterId) return false;
    if (this.viewMode === 'class') return !!this.selectedClassId;
    if (this.viewMode === 'teacher') return !!this.selectedTeacherId;
    if (this.viewMode === 'classroom') return !!this.selectedClassroomId;
    return false;
  }

  get currentViewTitle(): string {
    if (this.viewMode === 'class') {
      const cls = this.classes.find(c => c.id === this.selectedClassId);
      return cls ? `${cls.grade}年级 ${cls.name} 课表` : '';
    }
    if (this.viewMode === 'teacher') {
      const t = this.teachers.find(t => t.id === this.selectedTeacherId);
      return t ? `${t.name} 教师课表` : '';
    }
    if (this.viewMode === 'classroom') {
      const c = this.classrooms.find(c => c.id === this.selectedClassroomId);
      return c ? `${c.name} 教室课表` : '';
    }
    return '';
  }

  constructor(private api: ApiService) {}

  ngOnInit(): void {
    this.loadSemesters();
    this.loadClasses();
    this.loadTeachers();
    this.loadClassrooms();
  }

  loadSemesters(): void {
    this.api.getSemesters().subscribe(data => {
      this.semesters = data;
      const active = data.find(s => s.is_active);
      if (active) {
        this.selectedSemesterId = active.id;
        this.currentSemester = active;
        this.updatePeriodsFromSemester();
        this.loadSchedules();
      }
    });
  }

  loadClasses(): void {
    this.api.getClasses().subscribe(data => {
      this.classes = data;
      if (data.length > 0 && !this.selectedClassId) {
        this.selectedClassId = data[0].id;
        if (this.selectedSemesterId) this.loadSchedules();
      }
    });
  }

  loadTeachers(): void {
    this.api.getTeachers().subscribe(data => {
      this.teachers = data;
      if (data.length > 0 && !this.selectedTeacherId) {
        this.selectedTeacherId = data[0].id;
      }
    });
  }

  loadClassrooms(): void {
    this.api.getClassrooms().subscribe(data => {
      this.classrooms = data;
      if (data.length > 0 && !this.selectedClassroomId) {
        this.selectedClassroomId = data[0].id;
      }
    });
  }

  updatePeriodsFromSemester(): void {
    if (this.currentSemester?.daily_periods?.length) {
      this.periods = this.currentSemester.daily_periods
        .slice()
        .sort((a, b) => a.order - b.order);
      const dayCount = Math.min(7, Math.max(1, this.currentSemester.weekly_days || 5));
      this.weekDayNumbers = Array.from({ length: dayCount }, (_, i) => i + 1);
      this.weekDays = this.weekDayNumbers.map(d => this.weekDayName(d));
    }
  }

  weekDayName(day: number): string {
    return ['', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日'][day];
  }

  onSemesterChange(): void {
    if (this.selectedSemesterId) {
      this.currentSemester = this.semesters.find(s => s.id === this.selectedSemesterId) || null;
      this.updatePeriodsFromSemester();
      this.clearSwapSelection();
      this.loadSchedules();
    }
  }

  loadSchedules(): void {
    if (!this.selectedSemesterId) return;

    let obs;
    if (this.viewMode === 'class' && this.selectedClassId) {
      obs = this.api.getSchedulesByClass(this.selectedSemesterId, this.selectedClassId);
    } else if (this.viewMode === 'teacher' && this.selectedTeacherId) {
      obs = this.api.getSchedulesByTeacher(this.selectedSemesterId, this.selectedTeacherId);
    } else if (this.viewMode === 'classroom' && this.selectedClassroomId) {
      obs = this.api.getSchedulesByClassroom(this.selectedSemesterId, this.selectedClassroomId);
    } else {
      obs = this.api.getSchedulesBySemester(this.selectedSemesterId);
    }

    obs.subscribe(data => {
      this.schedules = data;
      // 切换视角/刷新后，若选中的课不在当前视图则清除选择
      if (this.selectedSwapEntry && !data.some((e: ScheduleEntry) => e.id === this.selectedSwapEntry!.id)) {
        this.selectedSwapEntry = null;
      }
    });
  }

  getEntryAt(day: number, period: number): ScheduleEntry[] {
    return this.schedules.filter(e => e.day_of_week === day && e.period === period);
  }

  hasSuspensionFlag(entry: ScheduleEntry): boolean {
    return !!entry.suspension_flags && entry.suspension_flags.length > 0;
  }

  clearSwapSelection(): void {
    this.selectedSwapEntry = null;
  }

  onEntryClick(entry: ScheduleEntry): void {
    if (!this.selectedSwapEntry) {
      this.selectedSwapEntry = entry;
      return;
    }
    if (this.selectedSwapEntry.id === entry.id) {
      this.clearSwapSelection();
      return;
    }
    const first = this.selectedSwapEntry;
    this.clearSwapSelection();
    this.requestSwap(first, entry, false);
  }

  requestSwap(entry1: ScheduleEntry, entry2: ScheduleEntry, force: boolean): void {
    this.api.validateSwap(entry1.id, entry2.id).subscribe({
      next: (result) => {
        if (result.valid) {
          this.executeSwap(entry1, entry2, false, result.issues);
          return;
        }
        const errors = result.issues.filter(i => i.severity === 'error');
        const warnings = result.issues.filter(i => i.severity === 'warning');

        if (errors.length > 0) {
          // 停排、跨学期等硬约束：不允许互换
          alert(
            `无法互换，存在以下问题：\n\n${errors.map(i => '• ' + i.message).join('\n')}` +
            (warnings.length
              ? `\n\n同时提示：\n${warnings.map(i => '• ' + i.message).join('\n')}`
              : '')
          );
          return;
        }

        if (warnings.length > 0) {
          const confirmed = confirm(
            `互换存在以下风险：\n\n${warnings.map(i => '• ' + i.message).join('\n')}\n\n` +
            `是否仍然强制互换？`
          );
          if (!confirmed) return;
        }
        this.executeSwap(entry1, entry2, true, result.issues);
      },
      error: () => alert('互换校验失败，请稍后重试')
    });
  }

  executeSwap(entry1: ScheduleEntry, entry2: ScheduleEntry, force: boolean, issues: SwapIssue[]): void {
    this.api.swapEntries(entry1.id, entry2.id, undefined, force).subscribe({
      next: () => {
        this.loadSchedules();
      },
      error: (err: HttpErrorResponse) => {
        const serverIssues: SwapIssue[] = err?.error?.issues || [];
        if (serverIssues.length > 0) {
          alert(
            `互换被拒绝：\n\n${serverIssues.map(i => '• ' + i.message).join('\n')}`
          );
        } else {
          alert(err?.error?.error || '互换失败');
        }
      }
    });
  }

  runAutoSchedule(respectLocked = true): void {
    if (!this.selectedSemesterId) return;
    this.schedulingMessage = '正在自动排课，请稍候...';
    this.lockedWarnings = [];

    this.api.autoSchedule(this.selectedSemesterId, respectLocked).subscribe(result => {
      const total = result.total_entries || 0;
      const conflicts = (result.conflicts || []).length;
      const messages = result.scheduling_messages || [];

      let msg = `排课完成！共安排 ${total} 节课`;
      if (conflicts > 0) {
        msg += `，发现 ${conflicts} 个冲突`;
      }
      if (messages.length > 0) {
        msg += `。提示: ${messages.map((m: any) => m.message).join('; ')}`;
      }
      this.schedulingMessage = msg;
      this.lockedWarnings = result.locked_suspension_warnings || [];
      this.loadSchedules();
    });
  }

  toggleLock(entry: ScheduleEntry): void {
    this.api.updateScheduleEntry(entry.id, { is_locked: !entry.is_locked }).subscribe(() => {
      entry.is_locked = !entry.is_locked;
    });
  }

  exportPdf(): void {
    if (!this.selectedSemesterId) return;
    let type: 'class' | 'teacher' | 'classroom' = 'class';
    let id = 0;

    if (this.viewMode === 'class' && this.selectedClassId) {
      type = 'class';
      id = this.selectedClassId;
    } else if (this.viewMode === 'teacher' && this.selectedTeacherId) {
      type = 'teacher';
      id = this.selectedTeacherId;
    } else if (this.viewMode === 'classroom' && this.selectedClassroomId) {
      type = 'classroom';
      id = this.selectedClassroomId;
    } else {
      return;
    }

    this.api.exportPdf(this.selectedSemesterId, type, id).subscribe(blob => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'timetable.pdf';
      a.click();
      URL.revokeObjectURL(url);
    });
  }

  async exportImage(): Promise<void> {
    try {
      const html2canvas = (await import('html2canvas')).default;
      const element = this.timetableContainer.nativeElement;
      const canvas = await html2canvas(element, {
        backgroundColor: '#ffffff',
        scale: 2
      });
      const link = document.createElement('a');
      link.download = 'timetable.png';
      link.href = canvas.toDataURL();
      link.click();
    } catch (e) {
      alert('图片导出功能需要 html2canvas 库');
      console.error(e);
    }
  }
}
