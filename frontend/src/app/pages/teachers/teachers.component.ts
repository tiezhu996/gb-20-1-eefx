import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { MatTableModule } from '@angular/material/table';
import { MatButtonModule } from '@angular/material/button';
import { MatInputModule } from '@angular/material/input';
import { MatIconModule } from '@angular/material/icon';
import { MatSelectModule } from '@angular/material/select';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { ApiService } from '../../services/api.service';
import type { Teacher, Semester, TeacherSuspension } from '../../types';

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
    MatIconModule,
    MatSelectModule,
    MatCardModule,
    MatChipsModule,
    MatCheckboxModule
  ],
  template: `
    <div class="page-container">
      <h1 class="page-title">教师管理</h1>

      <!-- ========== 教师列表 ========== -->
      <ng-container *ngIf="viewMode === 'list'">
        <div class="action-bar">
          <button mat-raised-button color="primary" (click)="startCreate()">
            <mat-icon>add</mat-icon>
            新建教师
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
                <button mat-icon-button color="primary" (click)="startEdit(item)" title="编辑">
                  <mat-icon>edit</mat-icon>
                </button>
                <button mat-raised-button color="accent"
                        (click)="openSuspensions(item)"
                        [disabled]="!item.is_active">
                  <mat-icon>event_busy</mat-icon>
                  临时停排
                </button>
                <button mat-icon-button color="warn" (click)="deleteItem(item)" title="删除">
                  <mat-icon>delete</mat-icon>
                </button>
              </td>
            </ng-container>

            <tr mat-header-row *matHeaderRowDef="displayedColumns"></tr>
            <tr mat-row *matRowDef="let row; columns: displayedColumns;"></tr>
          </table>
        </div>
      </ng-container>

      <!-- ========== 临时停排管理 ========== -->
      <ng-container *ngIf="viewMode === 'suspensions' && selectedTeacher">
        <div class="action-bar">
          <button mat-button (click)="backToList()">
            <mat-icon>arrow_back</mat-icon>
            返回教师列表
          </button>
        </div>

        <h2 class="page-title">
          <mat-icon style="vertical-align: middle;">event_busy</mat-icon>
          {{ selectedTeacher.name }}（{{ selectedTeacher.subject }}）— 临时停排
        </h2>
        <p class="suspension-tip">
          登记教师请假、校外培训等不可排课的时段：选择具体日期与连续节次并填写原因。
          重新生成课表时会自动避开；已登记的停排可随时取消。
        </p>

        <mat-card class="suspension-form-card">
          <mat-card-content>
            <h3>登记停排</h3>
            <form [formGroup]="suspensionForm" (ngSubmit)="submitSuspension()" class="suspension-form">
              <mat-form-field>
                <mat-label>学期</mat-label>
                <mat-select formControlName="semester" (selectionChange)="onSemesterSelected()">
                  <mat-option *ngFor="let s of semesters" [value]="s.id">
                    {{ s.name }}
                    <span *ngIf="s.is_active" style="color: green;">（当前）</span>
                  </mat-option>
                </mat-select>
              </mat-form-field>

              <mat-form-field>
                <mat-label>停排日期</mat-label>
                <input matInput type="date" formControlName="date" required>
              </mat-form-field>

              <mat-form-field>
                <mat-label>起始节次</mat-label>
                <mat-select formControlName="start_period" required>
                  <mat-option *ngFor="let p of periodOptions" [value]="p.order">
                    第{{ p.order }}节{{ p.name ? '（' + p.name + '）' : '' }}
                  </mat-option>
                </mat-select>
              </mat-form-field>

              <mat-form-field>
                <mat-label>连续几节</mat-label>
                <mat-select formControlName="period_count" required>
                  <mat-option *ngFor="let n of periodCountOptions" [value]="n">{{ n }} 节</mat-option>
                </mat-select>
              </mat-form-field>

              <mat-form-field class="reason-field">
                <mat-label>原因（请假 / 校外培训等）</mat-label>
                <textarea matInput formControlName="reason" rows="2" required></textarea>
              </mat-form-field>

              <div class="suspension-submit">
                <button mat-raised-button color="primary" type="submit"
                        [disabled]="suspensionForm.invalid || submitting">
                  <mat-icon>save</mat-icon>
                  登记
                </button>
                <span *ngIf="formError" class="form-error">{{ formError }}</span>
              </div>
            </form>
          </mat-card-content>
        </mat-card>

        <h3 style="margin-top: 24px;">停排记录</h3>
        <div class="table-container">
          <table mat-table [dataSource]="suspensions" class="mat-elevation-z8">
            <ng-container matColumnDef="date">
              <th mat-header-cell *matHeaderCellDef>日期</th>
              <td mat-cell *matCellDef="let s">
                {{ s.date }}（{{ weekdayLabel(s.date) }}）
              </td>
            </ng-container>

            <ng-container matColumnDef="periods">
              <th mat-header-cell *matHeaderCellDef>节次</th>
              <td mat-cell *matCellDef="let s">
                第{{ s.start_period }}-{{ s.end_period }}节（连续{{ s.period_count }}节）
              </td>
            </ng-container>

            <ng-container matColumnDef="reason">
              <th mat-header-cell *matHeaderCellDef>原因</th>
              <td mat-cell *matCellDef="let s">{{ s.reason }}</td>
            </ng-container>

            <ng-container matColumnDef="status">
              <th mat-header-cell *matHeaderCellDef>状态</th>
              <td mat-cell *matCellDef="let s">
                <mat-chip *ngIf="s.is_active" color="warn" selected>生效中</mat-chip>
                <mat-chip *ngIf="!s.is_active">已取消</mat-chip>
              </td>
            </ng-container>

            <ng-container matColumnDef="actions">
              <th mat-header-cell *matHeaderCellDef>操作</th>
              <td mat-cell *matCellDef="let s">
                <button mat-raised-button color="warn"
                        *ngIf="s.is_active"
                        (click)="cancelSuspension(s)">
                  <mat-icon>cancel</mat-icon>
                  取消停排
                </button>
                <span *ngIf="!s.is_active" class="muted">—</span>
              </td>
            </ng-container>

            <tr mat-header-row *matHeaderRowDef="suspensionColumns"></tr>
            <tr mat-row *matRowDef="let row; columns: suspensionColumns;"></tr>
          </table>
          <p *ngIf="suspensions.length === 0" class="muted" style="padding: 12px;">
            暂无停排记录。
          </p>
        </div>
      </ng-container>
    </div>
  `,
  styles: [`
    .full-width-field { width: 100%; }
    .suspension-tip { color: #666; margin-bottom: 16px; }
    .suspension-form-card { margin-bottom: 16px; }
    .suspension-form {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: flex-start;
    }
    .suspension-form mat-form-field { min-width: 160px; }
    .suspension-form .reason-field { min-width: 280px; flex: 1; }
    .suspension-submit {
      display: flex;
      align-items: center;
      gap: 12px;
      padding-top: 8px;
    }
    .form-error { color: #f44336; font-size: 13px; }
    .muted { color: #999; }
    .action-cell { display: flex; gap: 6px; align-items: center; }
  `]
})
export class TeachersComponent implements OnInit {
  displayedColumns: string[] = ['name', 'subject', 'phone', 'email', 'is_active', 'actions'];
  suspensionColumns: string[] = ['date', 'periods', 'reason', 'status', 'actions'];
  dataSource: Teacher[] = [];
  showForm = false;
  editingId: number | null = null;
  form: FormGroup;

  // 临时停排
  viewMode: 'list' | 'suspensions' = 'list';
  selectedTeacher: Teacher | null = null;
  semesters: Semester[] = [];
  suspensions: TeacherSuspension[] = [];
  suspensionForm: FormGroup;
  submitting = false;
  formError = '';
  periodOptions: { order: number; name?: string }[] = [];

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
      semester: [null, Validators.required],
      date: [null, Validators.required],
      start_period: [1, Validators.required],
      period_count: [1, Validators.required],
      reason: ['', Validators.required]
    });
  }

  ngOnInit(): void {
    this.loadData();
  }

  loadData(): void {
    this.api.getTeachers().subscribe(data => {
      this.dataSource = data;
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

  // ================= 临时停排 =================

  openSuspensions(teacher: Teacher): void {
    this.selectedTeacher = teacher;
    this.viewMode = 'suspensions';
    this.formError = '';
    this.suspensions = [];
    this.api.getSemesters().subscribe(semesters => {
      this.semesters = semesters;
      const active = semesters.find(s => s.is_active) || semesters[0];
      if (active) {
        this.suspensionForm.patchValue({ semester: active.id });
        this.updatePeriodOptions(active);
      }
      this.loadSuspensions();
    });
  }

  backToList(): void {
    this.viewMode = 'list';
    this.selectedTeacher = null;
  }

  onSemesterSelected(): void {
    const sem = this.semesters.find(s => s.id === this.suspensionForm.value.semester);
    if (sem) this.updatePeriodOptions(sem);
  }

  updatePeriodOptions(semester: Semester): void {
    if (semester.daily_periods && semester.daily_periods.length > 0) {
      this.periodOptions = semester.daily_periods
        .slice()
        .sort((a, b) => a.order - b.order)
        .map(p => ({ order: p.order, name: p.name }));
    } else {
      this.periodOptions = Array.from({ length: 7 }, (_, i) => ({ order: i + 1 }));
    }
    // 起始节次变化后若连续节数超出范围则收敛
    const start = this.suspensionForm.value.start_period || 1;
    const maxCount = this.periodOptions.length - start + 1;
    if (this.suspensionForm.value.period_count > maxCount) {
      this.suspensionForm.patchValue({ period_count: Math.max(1, maxCount) });
    }
  }

  get periodCountOptions(): number[] {
    const start = this.suspensionForm.value.start_period || 1;
    const maxCount = Math.max(1, this.periodOptions.length - start + 1);
    return Array.from({ length: maxCount }, (_, i) => i + 1);
  }

  loadSuspensions(): void {
    if (!this.selectedTeacher) return;
    this.api.getTeacherSuspensions({ teacherId: this.selectedTeacher.id })
      .subscribe(data => {
        this.suspensions = data.sort((a, b) =>
          b.date.localeCompare(a.date) || a.start_period - b.start_period
        );
      });
  }

  submitSuspension(): void {
    if (this.suspensionForm.invalid || !this.selectedTeacher) return;
    const v = this.suspensionForm.value;
    this.submitting = true;
    this.formError = '';
    this.api.createTeacherSuspension({
      teacher: this.selectedTeacher.id,
      semester: v.semester,
      date: v.date,
      start_period: v.start_period,
      period_count: v.period_count,
      reason: (v.reason || '').trim()
    }).subscribe({
      next: () => {
        this.submitting = false;
        this.suspensionForm.patchValue({ date: null, start_period: 1, period_count: 1, reason: '' });
        this.loadSuspensions();
      },
      error: err => {
        this.submitting = false;
        this.formError = this.extractError(err) || '登记失败，请检查输入';
      }
    });
  }

  cancelSuspension(s: TeacherSuspension): void {
    if (!confirm(`确定取消 ${s.date} 第${s.start_period}-${s.end_period}节的停排登记吗？取消后该时段恢复正常排课。`)) {
      return;
    }
    this.api.cancelTeacherSuspension(s.id).subscribe({
      next: () => this.loadSuspensions(),
      error: err => alert(this.extractError(err) || '取消失败')
    });
  }

  weekdayLabel(dateStr: string): string {
    const labels = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
    return labels[new Date(dateStr + 'T00:00:00').getDay()];
  }

  private extractError(err: any): string {
    if (!err?.error) return '';
    if (typeof err.error === 'string') return err.error;
    const e = err.error;
    if (e.detail) return String(e.detail);
    const parts: string[] = [];
    for (const key of ['date', 'start_period', 'period_count', 'reason', 'teacher', 'semester', '__all__']) {
      if (e[key]) parts.push(Array.isArray(e[key]) ? e[key].join('；') : String(e[key]));
    }
    return parts.join('；');
  }
}
