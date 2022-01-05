## 简介

**交流QQ群: 528735636**

Home Assistant的组件
此Home Assistant的组件可以让天猫精灵对接HomeAssistant平台,上报设备状态,天猫精灵查询HomeAssistan平台上的智能家居设备状态。

注意：本插件只负责上报HomeAssistent的设备状态信息到服务器，控制功能需要在HomeLife平台上配置。
## 声明

本组件基于MoloBot的代码，二次修改开发。
源项目地址：[MoloBot](https://github.com/haoctopus/molobot)

## 安装

- [下载插件](https://gitee.com/blear/HassLife)

>>1、下载`homelife`文件夹，保存在`<homeassistant配置目录>/custom_components/`目录中，若`custom_components`目录不存在则自行创建。

>>2、重启HomeAssistent,使插件生效【重要！先重启再配置hasslife信息,否则报错】。

>>3、编辑`<homeassistant配置目录>/configuration.yaml`文件，添加如下配置
```yaml
hasslife:
  username: "test"  # HassLife上注册的用户名
  password: "123456"    # 注册的密码
```

>>4、再次重启HomeAssistent

- homeassistant配置目录在哪?

>>**Windows用户:** `%APPDATA%\.homeassistant`

>>**Linux-based用户:** 可以通过执行`locate .homeassistant/configuration.yaml`命令，查找到的`.homeassistant`文件夹就是配置目录。

>>**群晖Docker用户:** 进入Docker - 映像 - homeassistant - 高级设置 - 卷, `/config`对应的路径就是配置目录


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

## 支持设备及属性

目前支持的设备类型有: 灯、开关、晾衣架、窗帘、电视、热水器、风扇、传感器、空调、二元选择器.

    设备的开关状态支持设备：灯、开关、晾衣架、窗帘、电视、热水器、风扇、传感器、空调、二元选择器.
    
	灯支持调整：颜色、亮度、色温
    
	空调支持更换模式：制冷、制热、送风、除湿、自动、温度调节。风速支持:低风、中风、高风、自动
    
	晾衣架支持：晾杆控制，开关控制
    
	窗帘支持：窗帘的打开关闭

        风扇支持：电源控制(打开/关闭风扇)、风速控制(1-100档(百分比风速)，最高档、抵挡、中低档、中高档、高档、超强档、微风档、自动挡)、左右旋转/摇头/摆风

