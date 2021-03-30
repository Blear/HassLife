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

>>2、编辑`<homeassistant配置目录>/custom_components/configuration.yaml`文件，添加如下配置
```yaml
hasslife:
  username: test  # HassLife上注册的用户名
  password: 123456    # 注册的密码
```


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
* 确认授权，返回我的TAB，智能家居下查看全部


