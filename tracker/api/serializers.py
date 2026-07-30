from rest_framework import serializers
from tracker.models import Employee, Meeting, Task, TaskChecklist

class EmployeeSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = Employee
        fields = ['id', 'name', 'employee_id', 'designation', 'email', 'profile_photo']

class MeetingSerializer(serializers.ModelSerializer):
    attendees = EmployeeSerializer(many=True, read_only=True)
    
    class Meta:
        model = Meeting
        fields = ['id', 'title', 'date', 'start_time', 'end_time', 'agenda', 'status', 'attendees']

class TaskSerializer(serializers.ModelSerializer):
    assigned_to = EmployeeSerializer(many=True, read_only=True)
    
    class Meta:
        model = Task
        fields = ['id', 'title', 'due_date', 'status', 'assigned_to']

class TaskChecklistSerializer(serializers.ModelSerializer):
    assigned_to = EmployeeSerializer(read_only=True)
    created_by = EmployeeSerializer(read_only=True)
    
    class Meta:
        model = TaskChecklist
        fields = ['id', 'title', 'description', 'status', 'assigned_to', 'created_by', 'created_at', 'updated_at']
