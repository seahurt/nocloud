from django.contrib import admin
from core.models import *


# Register your models here.
@admin.register(BaseImage)
class BaseImageAdmin(admin.ModelAdmin):
    list_display = ('name', 'osvar')


@admin.register(VM)
class VMAdmin(admin.ModelAdmin):
    list_display = ('name', 'base_img')


@admin.register(Config)
class ConfigAdmin(admin.ModelAdmin):
    list_display = ('name', 'value')
