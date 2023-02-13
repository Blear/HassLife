## 简介

**交流QQ群: 528735636**

Home Assistant的组件

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

此Home Assistant的组件可以让天猫精灵、小爱同学对接HomeAssistant平台上的设备,控制设备、查询上报设备状态。

注意：本插件只负责上报HomeAssistant的设备状态信息到服务器，控制功能需要在[HassLife](https://hass.blear.cn) 平台上配置。
## 声明

本组件基于MoloBot的代码，二次修改开发。
源项目地址：[MoloBot](https://github.com/haoctopus/molobot)

## 安装

### 1.安装插件

##### 方式1:hacs安装【推荐！】
>>侧边栏HACS-》集成=》搜索hasslife并点击下载

##### 方式2:手动下载[下载插件](https://gitee.com/blear/HassLife)
>>下载`hasslife`文件夹，保存在`<homeassistant配置目录>/custom_components/`目录中，若`custom_components`目录不存在则自行创建,然后重启HomeAssistant。
- homeassistant配置目录在哪?

>>**Windows用户:** `%APPDATA%\.homeassistant`

>>**Linux-based用户:** 可以通过执行`locate .homeassistant/configuration.yaml`命令，查找到的`.homeassistant`文件夹就是配置目录。

>>**群晖Docker用户:** 进入Docker - 映像 - homeassistant - 高级设置 - 卷, `/config`对应的路径就是配置目录


### 2.配置插件
##### 方式1:集成界面UI配置
>>**点击HomeAssistant侧边栏的配置=》集成=》右下角添加集成=》搜索hasslife并点击=》输入注册的hasslife账号密码点提交即可，插件第一次启动需要时间,请耐心等待。**

如遇到此集成不支持通过UI配置，如果您是从Home Assistant网站点击链接前来，请确保您运行的是最新版的Home Assistant提示。
可以手动添加帐号配置，然后重启HomeAssistent
##### 方式2:手动配置
手动配置方法：
编辑`<homeassistant配置目录>/configuration.yaml`文件，添加如下配置
```yaml
hasslife:
  username: "test"  # HassLife上注册的用户名
  password: "123456"    # 注册的密码
```

## 天猫精灵app中配置实例
* 打开[HassLife](https://hass.blear.cn) ,注册账号并登录
* 配置HomeAssistant的地址和长期令牌信息
* 进入设备列表,添加需要的设备信息
* 安装最新版`天猫精灵`APP
* 打开`天猫精灵`APP
* 点击`内容`TAB
* 点击`精灵技能`
* 搜索`HassLife`
* 点击`HassLife`
* 点击`绑定平台账号`
* 登录HassLife账户
* 确认授权，返回精灵家TAB，即可看到添加的设备

## 天猫精灵支持设备及属性

目前支持的设备类型有: 灯、开关、晾衣架、窗帘、电视、热水器、风扇、传感器、空调、二元选择器.

    设备的开关状态支持设备：灯、开关、晾衣架、窗帘、电视、热水器、风扇、传感器、空调、二元选择器.
    
    灯支持调整：颜色、亮度、色温
    
    空调支持更换模式：制冷、制热、送风、除湿、自动、温度调节。风速支持:低风、中风、高风、自动
    
	晾衣架支持：晾杆控制，开关控制
    
	窗帘支持：窗帘的打开关闭
    
	风扇支持：电源控制(打开/关闭风扇)、风速控制(1-3档，最高档、抵挡、中低档、中高档、高档、超强档、微风档、自动挡)、左右旋转/摇头/摆风

## 小爱同学配置实例
* 打开[HassLife](https://hass.blear.cn) ,注册账号并登录
* 配置HomeAssistant的地址和长期令牌信息
* 进入设备列表,添加需要的设备信息
* 安装最新版`米家`APP
* 打开`米家`APP
* 点击`我的`TAB
* 点击`其他平台设备`
* 找到`右上角的添加`
* 找到`HassLife`并点击
* 点击`绑定账号`
* 登录HassLife账户
* 确认授权，同步设备

## 小爱同学支持设备及属性

目前支持的设备类型有: 灯、开关、窗帘、风扇、空调.

    设备的开关状态支持设备：灯、开关、窗帘、风扇、空调.
    
	灯支持调整：颜色、亮度、色温
    
	空调支持更换模式：制冷、制热、送风、除湿、自动、温度调节。风速支持:低风、中风、高风、自动
    
	窗帘支持：窗帘的打开关闭
    
	风扇支持：电源控制(打开/关闭风扇)、风速控制(1-3档、左右旋转/摇头/摆风)
