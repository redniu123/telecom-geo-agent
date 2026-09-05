# 数据来源、许可与边界

公开地理背景来源：OpenStreetMap contributors，通过 Overpass API 获取。

- 署名：© OpenStreetMap contributors
- 数据许可：Open Database License (ODbL) 1.0
- 许可链接：https://opendatacommons.org/licenses/odbl/1-0/
- 版权与署名说明：https://www.openstreetmap.org/copyright

仓库内 `background/` 是从审计通过的公开数据按竞赛走廊范围生成的子集。`sites.geojson` 的站点是合成点；`network.geojson` 的几何沿公开道路坐标派生，但候选通道身份、管道/新建类型、容量、占用、状态、成本和场景角色全部是合成竞赛字段，不是现实运营商资产。

所有输出仅用于竞赛样例与本地研发，必须标注“竞赛样例 / 非正式施工图”。任何公开仓库、公开数据包、截图或视频发布前，须由负责人按发布时有效的 OSMF Attribution Guidelines 和 ODbL 分发义务再次人工复核。
