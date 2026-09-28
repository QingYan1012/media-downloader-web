/**
 * 网络嗅探 v1.2 — 通用站放宽：.ts 分片、带参 mp4、更多 CDN
 * 仍过滤埋点 / 过长假 URL / B站 pbp
 */
let API = "http://127.0.0.1:8765";
const API_CANDIDATES = ["http://127.0.0.1:8765", "http://localhost:8765"];
const ext = typeof browser !== "undefined" ? browser : chrome;

function discoverApi() {
  API_CANDIDATES.forEach(function (base) {
    try {
      fetch(base + "/api/status")
        .then(function (r) {
          if (r.ok) API = base;
        })
        .catch(function () {});
    } catch (_) {}
  });
}
discoverApi();
setInterval(discoverApi, 15000);

const tabMedia = new Map();

const BLOCK_SUBSTR = [
  "data.bilibili.com/log",
  "/log/web",
  "bvc.bilivideo.com/pbp",
  "/pbp/data",
  "mountaintoys",
  "google-analytics",
  "googlesyndication",
  "doubleclick",
  "googletagmanager",
  "cm.bilibili.com",
  "api.bilibili.com/x/report",
  "api.bilibili.com/x/click",
  "facebook.com/tr",
  "scorecardresearch",
  "hotjar",
  "sentry.io",
];

// 媒体扩展名（含 query）
const MEDIA_EXT =
  /\.(m3u8|mpd|mp4|m4v|flv|webm|m4a|mp3|aac|ogg|ts|m4s|mov|mkv|f4v)(\?|#|$)/i;
// 伪装成 .txt 的 HLS 播放列表
const HLS_TXT =
  /\/(master|index|playlist|chunklist)[^/]*\.(txt|m3u)(\?|#|$)|\/hls\d?\/|\.urlset\//i;

// 通用 CDN / 流关键词（非 B 站也覆盖）
const CDN_HINT =
  /bilivideo\.com|upos-|mcdn\.bilivideo|googlevideo|douyinvod|bytefcdn|xhscdn|tiktokcdn|bytecdn|bdstatic|qnqcdn|aliyuncs\.com|myqcloud|cloudfront\.net|akamai|fastly|cdn\.|\/hls\/|\/hls3\/|\.urlset|\/dash\/|\/video\/|\/media\/|playlist\.m3u8|index\.m3u8|master\.txt|chunklist|seg-\d+|segment\d+|\.ts\?|mpegts|videoplayback|playurl|stream\.|vod\.|media\.|player\.|get_video|download_video|simplecookinghacks/i;

// Content-Type 判定
const CT_MEDIA =
  /mpegurl|m3u8|mp4|video\/|audio\/|dash\+xml|octet-stream|mpegts|mp2t|x-m4v|x-flv|webm/i;

const AUDIO_QN = /(^|[-_])(30280|30002|30277|30112|30216|30232|30250)([-_.?]|$)/;
const VIDEO_QN =
  /(^|[-_])(30016|30032|30064|30080|30077|100022|100024|100026|100028|100029|100030)([-_.?]|$)/;

function guessKind(url, contentType) {
  const u = (url || "").toLowerCase();
  const ct = (contentType || "").toLowerCase();
  if (ct.includes("audio") || AUDIO_QN.test(u) || /\.(mp3|m4a|aac|ogg)(\?|#|$)/.test(u))
    return "audio";
  if (
    u.includes(".m3u8") ||
    u.includes("mpegurl") ||
    ct.includes("mpegurl") ||
    /\/(master|index|playlist)[^/]*\.(txt|m3u)(\?|#|$)/.test(u) ||
    (u.includes("/hls") && u.includes(".urlset")) ||
    (u.includes("/hls") && u.endsWith(".txt"))
  )
    return "hls";
  if (u.includes(".mpd") || ct.includes("dash")) return "dash";
  if (/\.ts(\?|#|$)/.test(u) || ct.includes("mp2t") || ct.includes("mpegts")) return "ts";
  if (u.includes(".m4s")) return VIDEO_QN.test(u) || !AUDIO_QN.test(u) ? "video" : "audio";
  if (/\.(mp4|m4v|flv|webm|mov|mkv|f4v)(\?|#|$)/.test(u) || ct.includes("video")) return "video";
  if (/bilivideo|upos-|googlevideo|douyinvod|bytefcdn/.test(u)) return "video";
  return "media";
}

function isBlocked(url) {
  if (!url || typeof url !== "string") return true;
  if (!(url.startsWith("http://") || url.startsWith("https://"))) return true;
  if (url.length > 4000) return true;
  const low = url.toLowerCase();
  for (let i = 0; i < BLOCK_SUBSTR.length; i++) {
    if (low.includes(BLOCK_SUBSTR[i])) return true;
  }
  // 静态资源
  if (/\.(js|css|woff2?|ttf|eot|png|jpe?g|gif|svg|ico|webp|map)(\?|#|$)/i.test(low)) return true;
  // 明显非媒体 API
  if (/\/api\/(v\d\/)?(log|report|click|stats|analytics)/i.test(low)) return true;
  return false;
}

function shouldKeep(url, contentType) {
  if (isBlocked(url)) return false;
  if (MEDIA_EXT.test(url)) return true;
  if (typeof HLS_TXT !== "undefined" && HLS_TXT.test(url)) return true;
  if (CDN_HINT.test(url)) return true;
  if (contentType && CT_MEDIA.test(contentType)) {
    return true;
  }
  return false;
}

function dedupeKey(url) {
  try {
    const u = new URL(url);
    // 分片 ts 保留完整 path；签名 query 去掉常见 token 再比
    let path = u.hostname + u.pathname;
    // 同一 m3u8/mp4 不同 e= 签名视为同一资源
    if (/\.(m3u8|mp4|m4s|mpd)$/i.test(u.pathname)) return path.toLowerCase();
    // ts 分片 path 通常已唯一
    if (/\.ts$/i.test(u.pathname)) return path.toLowerCase();
    return path.toLowerCase();
  } catch (_) {
    return (url || "").split("?")[0].toLowerCase();
  }
}

function addMedia(tabId, url, kind, extra) {
  if (tabId == null || tabId < 0) return;
  if (!shouldKeep(url, extra && extra.ct)) return;
  url = String(url).split("#")[0];
  if (!tabMedia.has(tabId)) tabMedia.set(tabId, new Map());
  const map = tabMedia.get(tabId);
  const key = dedupeKey(url);
  for (const [, v] of map.entries()) {
    if (dedupeKey(v.url) === key) return;
  }
  // 限制单页数量，避免塞满 ts 分片
  if (map.size >= 120) {
    // 优先丢掉最老的纯 ts 分片
    let oldestTs = null;
    for (const [k, v] of map.entries()) {
      if (v.kind === "ts" && (!oldestTs || v.ts < oldestTs.ts)) oldestTs = { k: k, ts: v.ts };
    }
    if (oldestTs) map.delete(oldestTs.k);
    else if (map.size >= 150) return;
  }
  map.set(url, {
    url: url,
    kind: kind || guessKind(url, extra && extra.ct),
    ts: Date.now(),
  });
}

function listMedia(tabId) {
  const map = tabMedia.get(tabId);
  if (!map) return [];
  const order = { hls: 0, dash: 1, video: 2, audio: 3, ts: 4, media: 9 };
  let items = Array.from(map.values());
  // 若同时有 m3u8 和大量 ts，列表里 ts 折叠提示：只保留少量 ts 样例
  const hasHls = items.some(function (x) {
    return x.kind === "hls";
  });
  if (hasHls) {
    const tsItems = items.filter(function (x) {
      return x.kind === "ts";
    });
    if (tsItems.length > 3) {
      items = items.filter(function (x) {
        return x.kind !== "ts";
      });
      items.push({
        url: tsItems[0].url,
        kind: "ts",
        ts: tsItems[0].ts,
        note: "另有 " + tsItems.length + " 个 .ts 分片（已有 m3u8 时请优先下 m3u8）",
      });
    }
  }
  items.sort(function (a, b) {
    return (order[a.kind] || 9) - (order[b.kind] || 9);
  });
  return items;
}

function onRequest(details) {
  if (!details || details.tabId < 0) return;
  const url = details.url || "";
  if (shouldKeep(url)) addMedia(details.tabId, url, guessKind(url));
}

try {
  ext.webRequest.onCompleted.addListener(onRequest, { urls: ["<all_urls>"] }, []);
} catch (e) {
  console.warn(e);
}

try {
  ext.webRequest.onResponseStarted.addListener(onRequest, { urls: ["<all_urls>"] }, []);
} catch (e) {
  /* 部分浏览器无此事件 */
}

try {
  ext.webRequest.onHeadersReceived.addListener(
    function (d) {
      if (d.tabId < 0 || isBlocked(d.url)) return;
      const ct =
        ((d.responseHeaders || []).find(function (h) {
          return h.name && h.name.toLowerCase() === "content-type";
        }) || {}).value || "";
      if (shouldKeep(d.url, ct) || CT_MEDIA.test(ct)) {
        addMedia(d.tabId, d.url, guessKind(d.url, ct), { ct: ct });
      }
    },
    { urls: ["<all_urls>"] },
    ["responseHeaders"]
  );
} catch (e) {
  console.warn(e);
}

// 发送前：若有大量 ts 且有 m3u8，默认只发 m3u8/mp4/m4s
function preferUrls(urls) {
  const list = (urls || []).filter(function (u) {
    return u && !isBlocked(u);
  });
  const hls = list.filter(function (u) {
    return /\.m3u8(\?|#|$)/i.test(u);
  });
  const mp4 = list.filter(function (u) {
    return /\.mp4(\?|#|$)/i.test(u);
  });
  const m4s = list.filter(function (u) {
    return /\.m4s(\?|#|$)/i.test(u);
  });
  if (hls.length || mp4.length || m4s.length) {
    return list.filter(function (u) {
      return !/\.ts(\?|#|$)/i.test(u);
    });
  }
  return list;
}

ext.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
  if (!msg) return false;
  if (msg.type === "getMedia") {
    sendResponse({ items: listMedia(msg.tabId) });
    return true;
  }
  if (msg.type === "clearMedia") {
    if (msg.tabId != null) tabMedia.delete(msg.tabId);
    sendResponse({ ok: true });
    return true;
  }
  if (msg.type === "pageMedia") {
    const tabId = (sender.tab && sender.tab.id) || msg.tabId;
    (msg.items || []).forEach(function (it) {
      if (it && it.url && !isBlocked(it.url)) addMedia(tabId, it.url, it.kind);
    });
    sendResponse({ ok: true, count: listMedia(tabId).length });
    return true;
  }
  if (msg.type === "sendToDownloader") {
    let urls = preferUrls(msg.urls || []);
    // 多个 HLS 时优先只发 master（避免下到 index 文本）
    const masters = urls.filter(function (u) {
      return /master\.(txt|m3u8|m3u)(\?|#|$)/i.test(u);
    });
    if (masters.length) {
      urls = masters;
    }
    const looksHls = urls.some(function (u) {
      return (
        /\.m3u8(\?|#|$)/i.test(u) ||
        /\/(master|index|playlist)[^/]*\.(txt|m3u)(\?|#|$)/i.test(u) ||
        /\/hls\d?\//i.test(u) ||
        /\.urlset/i.test(u)
      );
    });
    const opts = Object.assign(
      { use_hls_engine: true, bilibili_m4s: true, direct_cdn: true },
      msg.options || {}
    );
    if (looksHls) {
      opts.use_hls_engine = true;
      opts.direct_cdn = false; // 禁止把播放列表当二进制直存
    }
    fetch(API + "/api/sniff/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ urls: urls, options: opts }),
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        sendResponse({ ok: true, data: data });
      })
      .catch(function (e) {
        sendResponse({ ok: false, error: String(e) });
      });
    return true;
  }
  return false;
});

if (ext.tabs && ext.tabs.onRemoved) {
  ext.tabs.onRemoved.addListener(function (id) {
    tabMedia.delete(id);
  });
}


// —— 右键菜单：发送链接到下载器 ——
try {
  ext.contextMenus.removeAll(function () {
    ext.contextMenus.create({
      id: "md-send-link",
      title: "发送到 MediaDownloader",
      contexts: ["link", "video", "audio", "page"],
    });
  });
} catch (e) {
  console.warn("contextMenus", e);
}

if (ext.contextMenus && ext.contextMenus.onClicked) {
  ext.contextMenus.onClicked.addListener(function (info, tab) {
    var url = info.linkUrl || info.srcUrl || (tab && tab.url) || "";
    if (!url || !url.startsWith("http")) return;
    fetch(API + "/api/sniff/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        urls: [url],
        options: { use_hls_engine: true, queue_name: "sniff", skip_plugins: false },
      }),
    }).catch(function () {});
  });
}

// —— 下载拦截：把浏览器下载改送到本机队列（可在 storage 关闭）——
try {
  if (ext.downloads && ext.downloads.onCreated) {
    ext.downloads.onCreated.addListener(function (item) {
      try {
        ext.storage.local.get(["interceptDownloads"], function (st) {
          if (st && st.interceptDownloads === false) return;
          var url = item.url || "";
          if (!url.startsWith("http")) return;
          if (/\.(js|css|png|jpe?g|gif|svg|woff2?|ico)(\?|$)/i.test(url)) return;
          if (!/\.(mp4|m3u8|mkv|flv|webm|mp3|m4a|ts|m4s|zip|rar|7z|pdf)(\?|$)/i.test(url) && !/\/hls\//i.test(url))
            return;
          fetch(API + "/api/sniff/download", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              urls: [url],
              options: { direct_cdn: true, use_hls_engine: true, queue_name: "sniff" },
            }),
          })
            .then(function () {
              try {
                if (item.id != null) ext.downloads.cancel(item.id);
              } catch (_) {}
            })
            .catch(function () {});
        });
      } catch (_) {}
    });
  }
} catch (e) {
  console.warn("downloads", e);
}
