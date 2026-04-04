# 生成项目结构

```text
output/
├── data/
│   ├── project.json
│   └── playlist.json
├── music/
│   ├── playlist-brief.txt
│   └── playlist-order.txt
├── photos-web/
├── share/
│   ├── share-config.json
│   ├── server.js
│   └── public/
│       └── share.html
├── wedding-starry.html
└── README.md
```

说明：

- `project.json` 是正片与分享版共用的数据源
- `playlist.json` 只保存相对路径和顺序
- `share-config.json` 保存分享密码与服务端口
- `photos-web/` 与 `music/` 是项目级素材目录
