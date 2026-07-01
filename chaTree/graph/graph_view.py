"""QWebEngineView 加载 pyvis 图谱 HTML，通过 QWebChannel 实现双击导航。"""

from __future__ import annotations

import re

from PySide6.QtCore import QObject, Signal, Slot, QUrl
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView

from pyvis.network import Network


class _GraphBridge(QObject):
    """JS → Python 桥接对象。"""

    navigate_requested = Signal(str, str)    # conv_id, msg_id
    node_selected = Signal(str, str, str)    # conv_id, msg_id, node_id

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)

    @Slot(str, str)
    def navigate(self, conv_id: str, msg_id: str):
        """JS 端双击节点时调用。"""
        self.navigate_requested.emit(conv_id, msg_id)

    @Slot(str, str)
    def selectNode(self, conv_id: str, msg_id: str):
        """JS 端单击节点时调用。"""
        nid = f"{conv_id}::{msg_id}"
        self.node_selected.emit(conv_id, msg_id, nid)


# ── 注入到 pyvis HTML 中的 JavaScript ─────────────────────────────

_INJECTED_JS = r"""
<style>
/* 覆盖 Bootstrap + pyvis 默认样式，确保图谱占满整个 QWebEngineView */
html, body {
    width: 100% !important; height: 100% !important;
    margin: 0 !important; padding: 0 !important;
    overflow: hidden !important;
    background: #0f1117 !important;
}
.card, .card-body {
    width: 100% !important; height: 100% !important;
    margin: 0 !important; padding: 0 !important;
    border: none !important;
    background: #0f1117 !important;
}
#mynetwork {
    width: 100% !important; height: 100% !important;
    border: none !important;
    background: #0f1117 !important;
    position: absolute !important;
    top: 0; left: 0;
    float: none !important;
}
</style>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script>
// --- QWebChannel 桥接 + vis.js 事件 ---
(function() {
    var bridge = null;

    // 初始化 QWebChannel
    new QWebChannel(qt.webChannelTransport, function(channel) {
        bridge = channel.objects.bridge;
    });

    // 等待 vis.js network 就绪后绑定事件
    function bindEvents() {
        if (typeof network === 'undefined') {
            setTimeout(bindEvents, 200);
            return;
        }

        // 双击 → 导航到对话中的消息
        network.on("doubleClick", function(params) {
            if (params.nodes.length > 0) {
                var nodeId = params.nodes[0];
                var parts = nodeId.split("::", 2);
                if (bridge) {
                    bridge.navigate(parts[0], parts[1] || "");
                }
            }
        });

        // 单击 → 更新详情面板
        network.on("click", function(params) {
            if (params.nodes.length > 0) {
                var nodeId = params.nodes[0];
                var parts = nodeId.split("::", 2);
                if (bridge) {
                    bridge.selectNode(parts[0], parts[1] || "");
                }
            }
        });
    }

    // 在 DOM 就绪后开始等待 network
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            setTimeout(bindEvents, 300);
        });
    } else {
        setTimeout(bindEvents, 300);
    }
})();
</script>
"""


class GraphWebView(QWebEngineView):
    """加载 pyvis 图谱 HTML，处理节点双击导航。

    Signals:
        navigate_requested(conv_id, msg_id): 双击节点 → 主窗口跳转
        node_selected(conv_id, msg_id, node_id): 单击节点 → 详情面板
    """

    navigate_requested = Signal(str, str)
    node_selected = Signal(str, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(300, 200)
        self.setStyleSheet("background: #0f1117; border: none;")

        # ── QWebChannel 桥接 ──
        self._bridge = _GraphBridge(self)
        self._bridge.navigate_requested.connect(
            lambda cid, mid: self.navigate_requested.emit(cid, mid)
        )
        self._bridge.node_selected.connect(
            lambda cid, mid, nid: self.node_selected.emit(cid, mid, nid)
        )

        channel = QWebChannel(self)
        channel.registerObject("bridge", self._bridge)
        self.page().setWebChannel(channel)

        self._current_html: str = ""

    def load_graph(self, net: Network):
        """从 pyvis Network 生成 HTML、注入 QWebChannel、加载。

        Args:
            net: 已构建好的 pyvis Network 对象。
        """
        # pyvis 需要先调用 generate_html() 才会填充 .html 属性
        html = net.generate_html()

        # 注入 QWebChannel 脚本（在 </body> 之前）
        html = html.replace("</body>", _INJECTED_JS + "\n</body>")

        self._current_html = html
        self.setHtml(html, QUrl("about:blank"))

    def reload_graph(self, net: Network):
        """重新加载（筛选后重建的）图谱。"""
        self.load_graph(net)
