# 使用KVM和云镜像快速安装虚拟机


## 配置步骤

以CentOS7为主机的操作系统作为示例

#### 1. 安装必备软件
```bash
sudo yum install qemu-kvm libvirt virt-install bridge-utils virt-manager genisoimage
```
#### 2. 设置桥接网络
桥接网络可以使虚拟机加入到主机的子网中，使主机以外的机器可以访问

/etc/sysconfig/network-scripts/ifcfg-br0  （网桥配置）
```
DEVICE=br0
TYPE=Bridge
NM_CONTROLLED=no
BOOTPROTO=static
IPADDR=192.168.1.2
GATEWAY=192.168.1.1
NETMASK=255.255.255.0
DNS1=114.114.114.114
ONBOOT=yes
```
> IP配置根据实际情况修改

/etc/sysconfig/network-scripts/ifcfg-em4 (这里是物理网卡配置，名字需要根据真实情况修改)
```
DEVICE=em4
ONBOOT=yes
BRIDGE=br0
NM_CONTROLLED=no
```

然后启动
```
ifup br0
ifup em4
```
> 请使用ip 和ping来确认网络是畅通的


#### 3. 准备镜像
比如下边这个， Ubuntu22.04 KVM云镜像
```
https://cloud-images.ubuntu.com/jammy/20240426/jammy-server-cloudimg-amd64-disk-kvm.img
```
使用Qemu-img创建新的镜像
```bash
qemu-img create -f qcow2 -b jammy-server-cloudimg-amd64-disk-kvm.img  vm.img 1024G 
```

#### 4. 准备初始化的数据
云镜像使用cloud-init来进行初始化，KVM可以通用cdrom传入一个iso来传递初始化的配置

/path/to/meta-data
```
instance-id: iid-local01
network:
  version: 2
  ethernets:
     ens3:
        addresses: [192.168.1.100/24]
        gateway4: 192.168.1.1
        nameservers:
          addresses: [114.114.114.114, 223.5.5.5]
   
```
> 网卡名称不同的镜像可能不一样，ubuntu的都是ens3, centos7的是eth0
> 
> 如果不知道网卡名称，可以不设置网络，会自动配置成DHCP

/path/to/user-data
```
#cloud-config
ssh_authorized_keys:
  - ssh-rsa AAA.....
password: <密码>
chpasswd:
  expire: False
```

创建seed.iso
```bash
genisoimage -output seed.iso -volid cidata -rock meta-data user-data
```

#### 5. 创建虚拟机
```bash
virt-install --import --name=my-fist-vm \
--memory=1024 --vcpus=2 \
--disk vm.img,format=qcow2,bus=virtio \
--disk seed.iso,device=cdrom \
--network bridge=br0,model=virtio \
--os-type=linux --os-variant="Ubuntu16.04" --noautoconsole
```
> memory传入的数字单位是MB
> 
> os-variant在旧版本的virt-install中只支持到ubuntu16.04, 新版本可能会支持新的分支名

#### 6. 进入虚拟机，配置固定IP
默认的初始化配置，如果不知道网卡的名称，所以只能默认使用DHCP，这时需要通用virsh来进入console, 配置网络

查看所有运行的虚拟机：
```bash
virsh list
```

进入虚拟机终端:
```bash
virsh console <name>
```

如果想关闭cloud-init配置网络的功能可以在VM中的/etc/cloud/cloud.cfg.d/目录中创建以下文件：
99-disable-cloud-network-config.cfg
内容如下：
```
network:
  config: disabled
```


