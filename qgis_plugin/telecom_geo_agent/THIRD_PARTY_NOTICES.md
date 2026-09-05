# Third-party notices

The installable ZIP built by `scripts/build_qgis_plugin.py` vendors the locally
installed NetworkX package so the QGIS plugin does not need an online service at
runtime. NetworkX is distributed under the BSD 3-Clause License. The build
copies its complete `networkx-*.dist-info` directory, including
`licenses/LICENSE.txt`, into `p0_runtime/`.

- Project: NetworkX
- Official site: https://networkx.org/
- Source: https://github.com/networkx/networkx
- License: BSD 3-Clause
