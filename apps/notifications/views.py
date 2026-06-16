from rest_framework import viewsets, status
from .models import Notifications
from apps.notifications.serializers import NotificationSerializer
from .serializers import NotificationSerializer
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response

# Create your views here.

class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'delete', 'patch', 'post']

    def get_queryset(self):
        return Notifications.objects.filter(user=self.request.user).order_by('-created_at')

    @action(detail=True, methods=['patch'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=['is_read'])
        serializer = self.get_serializer(notification)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='mark-all-read')
    def mark_all_read(self, request):
        updated = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response(
            {'detail': 'Notifications marquees comme lues.', 'updated_count': updated},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['post'], url_path='bulk-delete')
    def bulk_delete(self, request):
        ids = request.data.get('ids', [])
        if not isinstance(ids, list):
            return Response(
                {'detail': 'Le champ ids doit etre une liste.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        valid_ids = []
        for value in ids:
            try:
                valid_ids.append(int(value))
            except (TypeError, ValueError):
                continue

        deleted_count, _ = self.get_queryset().filter(id__in=valid_ids).delete()
        return Response(
            {'detail': 'Notifications supprimees.', 'deleted_count': deleted_count},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['delete'], url_path='clear-all')
    def clear_all(self, request):
        deleted_count, _ = self.get_queryset().delete()
        return Response(
            {'detail': 'Toutes les notifications ont ete supprimees.', 'deleted_count': deleted_count},
            status=status.HTTP_200_OK,
        )