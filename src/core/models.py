import os

from django.db import models
from django.conf import settings
from pathlib import Path
import shutil
import subprocess


ConfigKeys = [
    "network",
    "gateway",
    "broadcast",
    "dns1",
    "dns2",
    "allow_password_auth",
    "password_expire"
]


class Config(models.Model):
    name_choices = ((key, key) for key in ConfigKeys)
    name = models.CharField(max_length=128, unique=True, choices=name_choices)
    description = models.CharField(max_length=256, null=True, blank=True)
    value = models.CharField(max_length=256, null=True, blank=True)

    def __str__(self):
        return self.name


class BaseImage(models.Model):
    _metadata_templ = """instance-id: iid-local01
network-interfaces: |
  auto {iface}
  iface {iface} inet static
  address {{ip}}
  network {{network}}
  netmask 255.255.255.0
  gateway {{gateway}}
  broadcast {{broadcast}}
  dns-nameservers {{dns1}},{{dns2}}
hostname: {hostname}
"""

    _userdata_templ = """#cloud-config
password: {{password}}
chpasswd: {{expire: {{password_expire}} }}
ssh_pwauth: {{allow_password_auth}}
ssh_authorized_keys:
  - {{ssh_keys}}
"""

    name = models.CharField(max_length=256, unique=True)
    path = models.CharField(max_length=256)
    format = models.CharField(max_length=32)  # qcow2
    ifname = models.CharField(max_length=32)
    hostname = models.CharField(max_length=64)
    osvar = models.CharField(max_length=32)
    config = models.JSONField(default=dict, null=True, blank=True)
    meta_data_template = models.TextField()
    user_data_template = models.TextField()

    def __str__(self):
        return self.name


class VM(models.Model):
    CREATED = '已创建'
    RUNNING = '运行中'
    SHUTDOWN = '关机'
    ERROR = '出错'
    name = models.CharField(max_length=128, unique=True)
    base_img = models.ForeignKey(BaseImage, on_delete=models.PROTECT)
    workdir = models.CharField(max_length=256)
    ip = models.GenericIPAddressField()
    disk_size = models.IntegerField("Disk Size(GB)", default=100)
    cpu = models.IntegerField("CPU", default=1)
    mem = models.IntegerField("MEM(GB)", default=1)
    config = models.JSONField(default=dict, null=True, blank=True)
    status = models.CharField(max_length=16, choices=())
    stdout = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.name

    def make_seed(self):
        sys_config = {}
        for item in ConfigKeys:
            cfg = Config.objects.filter(name=item).first()
            if cfg:
                sys_config = cfg.value
            else:
                sys_config = getattr(settings, item.upper())
        sys_config.update(self.config)
        network_data = self.base_img.meta_data_template.format(**sys_config)
        meta_data_path = Path(self.workdir) / 'meta_data.txt'
        meta_data_path.write_text(network_data)

        user_data = self.base_img.user_data_template.format(**sys_config)
        user_data_path = Path(self.workdir) / 'user_data.txt'
        user_data_path.write_text(user_data)
        cmd = f'genisoimage -output {self.workdir}/seed.iso -volid cidata ' \
              f'-joliet -rock {meta_data_path} {user_data_path}'
        stdout, ret = run_cmd(cmd)
        if not self.stdout:
            self.stdout = ''
        self.stdout += stdout
        self.save()
        if ret != 0:
            msg = stdout.strip().split('\n')[-1]
            raise ValueError(f"创建Seed失败: {msg}")

    @property
    def img(self):
        return Path(self.workdir) / 'os.img'

    @property
    def seed(self):
        return Path(self.workdir) / 'seed.iso'

    def make_image(self):
        target_file = Path(self.workdir) / 'os.img'
        shutil.copy(self.base_img.path, target_file)
        cmd = f'qemu-img resize {target_file} +{self.disk_size}GB'
        stdout, ret = run_cmd(cmd)
        if not self.stdout:
            self.stdout = ''
        self.stdout += stdout
        self.save()
        if ret != 0:
            msg = stdout.strip().split('\n')[-1]
            raise ValueError(f"创建Img失败: {msg}")

    def create_vm(self):
        self.stdout = ''
        Path(self.workdir).mkdir(exist_ok=True, parents=True)
        self.make_seed()
        self.make_image()
        cmd = f'virt-install --import ' \
              f' --name={self.name} ' \
              f' --memory={self.mem * 1024}' \
              f' --vcpus={self.cpu} ' \
              f' --disk {self.img},format={self.base_img.format},bus=virtio' \
              f' --disk {self.seed},device=cdrom' \
              f' --osinfo detect=on,name={self.base_img.osvar} ' \
              f' --noautoconsole'
        stdout, ret = run_cmd(cmd)
        self.stdout = stdout
        self.save()
        if ret != 0:
            msg = stdout.strip().split('\n')[-1]
            raise ValueError(f"创建虚拟机失败: {msg}")


def run_cmd(cmd):
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, encoding='utf-8')
    try:
        stdout, _ = p.communicate(timeout=60)
    except subprocess.TimeoutExpired:
        p.kill()
        stdout, _ = p.communicate()
    return stdout, p.returncode
