import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { MatTableModule } from '@angular/material/table';
import { MatButtonModule } from '@angular/material/button';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../../services/api.service';
import type { Teacher, TeacherSuspension, Semester } from '../../types';

@Component({
  selector: 'app-teachers',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ReactiveFormsModule,
    MatTableModule,
    MatButtonModule,
    MatInputModule,
    MatSelectModule,
    MatFormFieldModule,
    MatIconModule
  ],
  template: `
    <div class="page-container">
      <h1 class="page-title">教师管理</h1>

      <div class="action-bar">
        <button mat-raised-button color="primary" (click)="startCreate()">
          <mat-icon>add</mat-icon>
          新建教师
        </button>
        <button mat-raised-button color="accent" (click)="toggleSuspensionPanel()">
          <mat-icon>event_busy</mat-icon>
          临时停排登记
        </button>
        <button mat-button (click)="loadData()">
          <mat-icon>refresh</mat-icon>
          刷新
        </button>
      </div>

      <div *ngIf="showForm" class="form-container">
        <h3>{{ editingId ? '编辑教师' : '新建教师' }}</h3>
        <form [formGroup]="form" (ngSubmit)="save()">
          <mat-form-field class="full-width-field">
            <mat-label>姓名</mat-label>
            <input matInput formControlName="name" required>
          </mat-form-field>

          <mat-form-field class="full-width-field">
            <mat-label>学科</mat-label>
            <input matInput formControlName="subject" required>
          </mat-form-field>

          <mat-form-field class="full-width-field">
            <mat-label>电话</mat-label>
            <input matInput formControlName="phone">
          </mat-form-field>

          <mat-form-field class="full-width-field">
            <mat-label>邮箱</mat-label>
            <input matInput formControlName="email">
          </mat-form-field>

          <mat-checkbox formControlName="is_active">启用</mat-checkbox>

          <div>
            <button mat-raised-button color="primary" type="submit">保存</button>
            <button mat-button type="button" (click)="cancel()">取消</button>
          </div>
        </form>
      </div>

      <div *ngIf="showSuspensionPanel" class="form-container suspension-panel">
        <h3>登记临时停排</h3>
        <p class="suspension-hint">
          教师请假、校外培训等不在校时段可在此登记。重新生成课表时会自动避开这些时段，
          手工调课换入这些时段也会被拦截。
        </p>
        <form [formGroup]="suspensionForm" (ngSubmit)="saveSuspension()">
          <mat-form-field class="full-width-field">
            <mat-label>教师</mat-label>
            <mat-select formControlName="teacher" required>
              <mat-option *ngFor="let t of teachers" [value]="t.id">
                {{ t.name }}（{{ t.subject }}）
              </mat-option>
            </mat-select>
          </mat-form-field>

          <mat-form-field class="full-width-field">
            <mat-label>停排日期</mat-label>
            <input matInput type="date" formControlName="date" required>
          </mat-form-field>

          <div style="display: flex; gap: 12px;">
            <mat-form-field style="flex: 1;">
              <mat-label>起始节次</mat-label>
              <mat-select formControlName="start_period" required>
                <mat-option *ngFor="let p of periodOptions" [value]="p">第{{ p }}节</mat-option>
              </mat-select>
            </mat-form-field>

            <mat-form-field style="flex: 1;">
              <mat-label>连续节数</mat-label>
              <mat-select formControlName="period_count" required>
                <mat-option *ngFor="let n of periodCountOptions" [value]="n">{{ n }} 节</mat-option>
              </mat-select>
            </mat-form-field>
          </div>

          <mat-form-field class="full-width-field">
            <mat-label>停排原因</mat-label>
            <input matInput formControlName="reason"
                   placeholder="如：病假、校外培训、教研活动" required>
          </mat-form-field>

          <div *ngIf="suspensionError" class="suspension-error">{{ suspensionError }}</div>

          <div>
            <button mat-raised-button color="primary" type="submit">登记停排</button>
            <button mat-button type="button" (click)="showSuspensionPanel = false">收起</button>
          </div>
        </form>

        <h3 style="margin-top: 24px;">停排记录</h3>
        <div class="table-container">
          <table mat-table [dataSource]="suspensions" class="mat-elevation-z8">
            <ng-container matColumnDef="teacher_name">
              <th mat-header-cell *matHeaderCellDef>教师</th>
              <td mat-cell *matCellDef="let item">{{ item.teacher_name }}</td>
            </ng-container>

            <ng-container matColumnDef="date">
              <th mat-header-cell *matHeaderCellDef>日期</th>
              <td mat-cell *matCellDef="let item">
                {{ item.date }}（{{ weekDayLabel(item.day_of_week) }}）
              </td>
            </ng-container>

            <ng-container matColumnDef="periods">
              <th mat-header-cell *matHeaderCellDef>停排节次</th>
              <td mat-cell *matCellDef="let item">
                第{{ item.start_period }}-{{ item.end_period }}节（{{ item.period_count }}节）
              </td>
            </ng-container>

            <ng-container matColumnDef="reason">
              <th mat-header-cell *matHeaderCellDef>原因</th>
              <td mat-cell *matCellDef="let item">{{ item.reason }}</td>
            </ng-container>

            <ng-container matColumnDef="is_active">
              <th mat-header-cell *matHeaderCellDef>状态</th>
              <td mat-cell *matCellDef="let item">
                <span [class.suspension-active]="item.is_active"
                      [class.suspension-cancelled]="!item.is_active">
                  {{ item.is_active ? '生效中' : '已取消' }}
                </span>
              </td>
            </ng-container>

            <ng-container matColumnDef="actions">
              <th mat-header-cell *matHeaderCellDef>操作</th>
              <td mat-cell *matCellDef="let item">
                <button
                  *ngIf="item.is_active"
                  mat-stroked-button color="warn"
                  (click)="cancelSuspension(item)"
                >
                  <mat-icon>undo</mat-icon>
                  取消停排
                </button>
                <span *ngIf="!item.is_active">-</span>
              </td>
            </ng-container>

            <tr mat-header-row *matHeaderRowDef="suspensionColumns"></tr>
            <tr mat-row *matCellDef="let row; columns: suspensionColumns;"
                [class.row-cancelled]="!row.is_active"></tr>
          </table>
        </div>
      </div>

      <div class="table-container" *ngIf="!showForm">
        <table mat-table [dataSource]="dataSource" class="mat-elevation-z8">
          <ng-container matColumnDef="name">
            <th mat-header-cell *matHeaderCellDef>姓名</th>
            <td mat-cell *matCellDef="let item">{{ item.name }}</td>
          </ng-container>

          <ng-container matColumnDef="subject">
            <th mat-header-cell *matHeaderCellDef>学科</th>
            <td mat-cell *matCellDef="let item">{{ item.subject }}</td>
          </ng-container>

          <ng-container matColumnDef="phone">
            <th mat-header-cell *matHeaderCellDef>电话</th>
            <td mat-cell *matCellDef="let item">{{ item.phone || '-' }}</td>
          </ng-container>

          <ng-container matColumnDef="email">
            <th mat-header-cell *matHeaderCellDef>邮箱</th>
            <td mat-cell *matCellDef="let item">{{ item.email || '-' }}</td>
          </ng-container>

          <ng-container matColumnDef="is_active">
            <th mat-header-cell *matHeaderCellDef>状态</th>
            <td mat-cell *matCellDef="let item">{{ item.is_active ? '启用' : '禁用' }}</td>
          </ng-container>

          <ng-container matColumnDef="actions">
            <th mat-header-cell *matHeaderCellDef>操作</th>
            <td mat-cell *matCellDef="let item" class="action-cell">
              <button mat-icon-button color="primary" (click)="startEdit(item)">
                <mat-icon>edit</mat-icon>
              </button>
              <button mat-icon-button color="warn" (click)="deleteItem(item)">
                <mat-icon>delete</mat-icon>
              </button>
            </td>
          </ng-container>

          <tr mat-header-row *matHeaderRowDef="displayedColumns"></tr>
          <tr mat-row *matRowDef="let row; columns: displayedColumns;"></tr>
        </table>
      </div>
    </div>
  `
})
export class TeachersComponent implements OnInit {
  displayedColumns: string[] = ['name', 'subject', 'phone', 'email', 'is_active', 'actions'];
  suspensionColumns: string[] = ['teacher_name', 'date', 'periods', 'reason', 'is_active', 'actions'];
  dataSource: Teacher[] = [];
  teachers: Teacher[] = [];
  suspensions: TeacherSuspension[] = [];
  semesters: Semester[] = [];
  showForm = false;
  showSuspensionPanel = false;
  editingId: number | null = null;
  form: FormGroup;
  suspensionForm: FormGroup;
  suspensionError = '';
  totalPeriods = 7;
  weekDays = ['', '周一', '周二', '周三', '周四', '周五', '周六', '周日'];

  constructor(
    private api: ApiService,
    private fb: FormBuilder
  ) {
    this.form = this.fb.group({
      id: [null],
      name: ['', Validators.required],
      subject: ['', Validators.required],
      phone: [''],
      email: [''],
      available_time_slots: [[]],
      is_active: [true]
    });
    this.suspensionForm = this.fb.group({
      teacher: [null, Validators.required],
      date: [this.todayString(), Validators.required],
      start_period: [1, Validators.required],
      period_count: [1, Validators.required],
      reason: ['', Validators.required]
    });
  }

  get periodOptions(): number[] {
    return Array.from({ length: this.totalPeriods }, (_, i) => i + 1);
  }

  get periodCountOptions(): number[] {
    const start = this.suspensionForm?.value.start_period ?? 1;
    return Array.from({ length: Math.max(1, this.totalPeriods - start + 1) }, (_, i) => i + 1);
  }

  ngOnInit(): void {
    this.loadData();
    this.loadSemesters();
  }

  todayString(): string {
    const now = new Date();
    const month = `${now.getMonth() + 1}`.padStart(2, '0');
    const day = `${now.getDate()}`.padStart(2, '0');
    return `${now.getFullYear()}-${month}-${day}`;
  }

  loadData(): void {
    this.api.getTeachers().subscribe(data => {
      this.dataSource = data;
      this.teachers = data;
      if (!this.suspensionForm.value.teacher && data.length > 0) {
        this.suspensionForm.patchValue({ teacher: data[0].id });
      }
    });
    this.loadSuspensions();
  }

  loadSemesters(): void {
    this.api.getSemesters().subscribe(data => {
      this.semesters = data;
      const active = data.find(s => s.is_active);
      if (active?.daily_periods?.length) {
        this.totalPeriods = active.daily_periods.length;
      }
    });
  }

  loadSuspensions(): void {
    this.api.getTeacherSuspensions().subscribe(data => {
      this.suspensions = data;
    });
  }

  weekDayLabel(dayOfWeek?: number): string {
    return dayOfWeek ? this.weekDays[dayOfWeek] : '';
  }

  toggleSuspensionPanel(): void {
    this.showSuspensionPanel = !this.showSuspensionPanel;
    if (this.showSuspensionPanel) {
      this.loadSuspensions();
    }
  }

  saveSuspension(): void {
    if (this.suspensionForm.invalid) {
      this.suspensionError = '请完整填写教师、日期、节次和原因';
      return;
    }
    this.suspensionError = '';
    const value = this.suspensionForm.value;
    this.api.createTeacherSuspension({
      teacher: value.teacher,
      date: value.date,
      start_period: value.start_period,
      period_count: value.period_count,
      reason: value.reason
    }).subscribe({
      next: () => {
        this.suspensionForm.patchValue({
          start_period: 1,
          period_count: 1,
          reason: ''
        });
        this.loadSuspensions();
      },
      error: (err) => {
        const errors = err?.error;
        if (errors?.non_field_errors) {
          this.suspensionError = errors.non_field_errors.join('；');
        } else if (errors?.detail) {
          this.suspensionError = errors.detail;
        } else {
          this.suspensionError = '登记失败，请检查日期与节次是否合法';
        }
      }
    });
  }

  cancelSuspension(item: TeacherSuspension): void {
    if (!confirm(`确定取消 ${item.teacher_name} 在 ${item.date} 第${item.start_period}-${item.end_period}节的停排吗？\n取消后该时段恢复正常排课。`)) {
      return;
    }
    this.api.cancelTeacherSuspension(item.id).subscribe({
      next: () => this.loadSuspensions(),
      error: (err) => alert(err?.error?.message || '取消失败')
    });
  }

  startCreate(): void {
    this.editingId = null;
    this.form.reset({
      name: '',
      subject: '',
      phone: '',
      email: '',
      available_time_slots: [],
      is_active: true
    });
    this.showForm = true;
  }

  startEdit(item: Teacher): void {
    this.editingId = item.id;
    this.form.patchValue(item);
    this.showForm = true;
  }

  cancel(): void {
    this.showForm = false;
  }

  save(): void {
    if (this.form.invalid) {
      alert('请填写必填字段');
      return;
    }
    const data = this.form.value;
    if (this.editingId) {
      this.api.updateTeacher(this.editingId, data).subscribe(() => {
        this.showForm = false;
        this.loadData();
      });
    } else {
      delete data.id;
      this.api.createTeacher(data).subscribe(() => {
        this.showForm = false;
        this.loadData();
      });
    }
  }

  deleteItem(item: Teacher): void {
    if (confirm(`确定要删除教师 "${item.name}" 吗？`)) {
      this.api.deleteTeacher(item.id).subscribe(() => this.loadData());
    }
  }
}
