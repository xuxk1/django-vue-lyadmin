from django.core.management.base import BaseCommand
from apps.lyworkflow.models import WorkflowInstance, WorkflowTask
from apps.lyworkflow.engine import FlowEngine


class Command(BaseCommand):
    help = '重新为指定流程实例创建审批任务（用于测试多级审批）'

    def add_arguments(self, parser):
        parser.add_argument('instance_no', type=str, help='流程实例编号')

    def handle(self, *args, **kwargs):
        instance_no = kwargs['instance_no']
        
        try:
            # 查找流程实例
            instance = WorkflowInstance.objects.get(instance_no=instance_no)
            
            self.stdout.write(f'找到流程实例: {instance.instance_no}')
            self.stdout.write(f'  状态: {instance.get_status_display()}')
            self.stdout.write(f'  当前步骤: {instance.current_step}')
            self.stdout.write(f'  总步骤: {instance.total_steps}')
            
            # 删除现有的待审批任务
            old_tasks = WorkflowTask.objects.filter(instance=instance, status=0)
            if old_tasks.exists():
                self.stdout.write(f'\n删除 {old_tasks.count()} 个旧的待审批任务')
                old_tasks.delete()
            
            # 使用流程引擎重新创建任务
            self.stdout.write('\n使用流程引擎重新创建任务...')
            engine = FlowEngine(instance)
            
            # 根据 current_step 创建对应层级的任务
            engine._create_tasks_for_step(int(instance.current_step))
            
            # 检查新创建的任务
            new_tasks = WorkflowTask.objects.filter(instance=instance, status=0)
            self.stdout.write(f'\n新创建了 {new_tasks.count()} 个待审批任务:')
            for task in new_tasks:
                dept_name = task.approver.dept.name if task.approver.dept else '无部门'
                self.stdout.write(
                    f'  - 任务ID: {task.id}, 步骤: {task.step_order}, '
                    f'审批人: {task.approver.name} ({dept_name})'
                )
            
            self.stdout.write(self.style.SUCCESS('\n任务创建成功！'))
            
        except WorkflowInstance.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'未找到流程实例: {instance_no}'))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'创建任务失败: {str(e)}'))
            import traceback
            traceback.print_exc()
