const ext = typeof browser !== "undefined" ? browser : chrome;

async function getActiveTab() {
  const tabs = await ext.tabs.query({ active: true, currentWindow: true });
  return tabs && tabs[0];
}

function render(items) {
  const list = document.getElementById("list");
  if (!items.length) {
    list.innerHTML =
      '<div class="empty">暂无媒体<br/>请在本页<strong>播放几秒</strong>后再刷新<br/>B站应出现 bilivideo 的 m4s（视频+音频）</div>';
    list._items = [];
    return;
  }
  list.innerHTML = items
    .map(function (it, i) {
      const k = (it.kind || "media").toLowerCase();
      const note = it.note ? '<div class="hint" style="margin:0">' + it.note + '</div>' : '';
      return (
        '<div class="item"><input type="checkbox" data-i="' +
        i +
        '" checked /><div><div class="kind ' +
        k +
        '">' +
        k +
        '</div><div class="url">' +
        it.url +
        '</div>' + note + '</div></div>'
      );
    })
    .join('');
  list._items = items;
}

async function load() {
  const list = document.getElementById("list");
  list.innerHTML = "扫描中…";
  try {
    const tab = await getActiveTab();
    if (!tab || !tab.id) {
      list.innerHTML = '<div class="empty">无法获取当前标签页</div>';
      return;
    }
    try {
      await ext.tabs.sendMessage(tab.id, { type: "scanPage" });
    } catch (_) {
      try {
        if (ext.tabs.executeScript) {
          await ext.tabs.executeScript(tab.id, { file: "content.js", allFrames: true });
          await ext.tabs.sendMessage(tab.id, { type: "scanPage" });
        }
      } catch (_) {}
    }
    await new Promise(function (r) {
      setTimeout(r, 300);
    });
    ext.runtime.sendMessage({ type: "getMedia", tabId: tab.id }, function (res) {
      render((res && res.items) || []);
    });
  } catch (e) {
    list.innerHTML = '<div class="empty">失败: ' + e + "</div>";
  }
}

function setAll(checked) {
  document.querySelectorAll("#list input[type=checkbox]").forEach(function (el) {
    el.checked = checked;
  });
}

/** B站：每种 kind 各勾 1 条，优先非镜像重复 */
function smartSelect() {
  const list = document.getElementById("list");
  const items = list._items || [];
  const boxes = Array.from(document.querySelectorAll("#list input[type=checkbox]"));
  boxes.forEach(function (el) {
    el.checked = false;
  });
  const picked = { video: false, audio: false, hls: false };
  // 优先带 300xx 视频 / 30280 音频的
  const order = items
    .map(function (it, i) {
      return { it: it, i: i };
    })
    .sort(function (a, b) {
      const score = function (u, k) {
        let s = 0;
        if (k === "audio") s += 10;
        if (/30280|30002/.test(u)) s += 5;
        if (/30077|30032|30064|30016|100026|100022/.test(u)) s += 3;
        if (/bilivideo\.com/.test(u) && !/mcdn\.bilivideo/.test(u)) s += 1;
        if (/pbp\/data/.test(u)) s -= 20;
        return s;
      };
      return score(b.it.url, b.it.kind) - score(a.it.url, a.it.kind);
    });
  order.forEach(function (o) {
    const k = (o.it.kind || "video").toLowerCase();
    if (k === "audio" && !picked.audio) {
      boxes[o.i].checked = true;
      picked.audio = true;
    } else if ((k === "video" || k === "media") && !picked.video) {
      if (!/pbp\/data/i.test(o.it.url)) {
        boxes[o.i].checked = true;
        picked.video = true;
      }
    } else if (k === "hls" && !picked.hls) {
      boxes[o.i].checked = true;
      picked.hls = true;
    }
  });
}

document.getElementById("selAll").onclick = function () {
  setAll(true);
};
document.getElementById("selNone").onclick = function () {
  setAll(false);
};
document.getElementById("selSmart").onclick = smartSelect;
document.getElementById("refresh").onclick = load;
document.getElementById("send").onclick = function () {
  const list = document.getElementById("list");
  const items = list._items || [];
  const checked = Array.from(list.querySelectorAll("input[type=checkbox]:checked"))
    .map(function (el) {
      return items[Number(el.dataset.i)] && items[Number(el.dataset.i)].url;
    })
    .filter(Boolean);
  if (!checked.length) {
    alert("请勾选媒体（建议：智能勾选）");
    return;
  }
  ext.runtime.sendMessage(
    {
      type: "sendToDownloader",
      urls: checked,
      options: { use_hls_engine: true, bilibili_m4s: true, direct_cdn: true },
    },
    function (res) {
      if (res && res.ok) alert("已发送 " + checked.length + " 条到本机下载器");
      else
        alert(
          "发送失败: " +
            ((res && res.error) || "请确认本机下载器已启动 :8765")
        );
    }
  );
};

load();
