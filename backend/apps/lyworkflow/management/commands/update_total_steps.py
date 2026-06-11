from django.core.management.base import BaseCommand
from apps.lyworkflow.models import WorkflowInstance, WorkflowStep


class Command(BaseCommand):
    help = '更新所有流程实例的 total_steps 字段，考虑多级审批展开'

    def handle(self, *args, **kwargs):
        self.stdout.write('开始更新流程实例的 total_steps 字段...')
        
        instances = WorkflowInstance.objects.all()
        updated_count = 0
        
        for instance in instances:
            # 计算展开后的总步骤数
            total_steps = self._calculate_total_steps(instance.workflow_type)
            
            # 如果与当前值不同，则更新
            if instance.total_steps != total_steps:
                old_value = instance.total_steps
                instance.total_steps = total_steps
                instance.save(update_fields=['total_steps'])
                updated_count += 1
                self.stdout.write(
                    f'  更新流程 {instance.instance_no}: {old_value} -> {total_steps}'
                )
        
        self.stdout.write(self.style.SUCCESS(
            f'\n完成！共更新了 {updated_count} 个流程实例的 total_steps 字段'
        ))
    
    def _calculate_total_steps(self, workflow_type):
        """计算流程的总步骤数（考虑多级审批展开）"""
        total = 0
        steps = workflow_type.steps.all()
        
        for step in steps:
            # 如果是多级审批（approver_type=6），计算其层级数
            if step.approver_type == 6 and step.multi_level_config:
                total += len(step.multi_level_config)
            else:
                # 普通步骤，计为1
                total += 1
        
        return total
