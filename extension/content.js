/**
 * 页面内嗅探 v1.2：fetch/XHR/Performance/DOM，放宽 mp4?query / .ts
 */
(function () {
  if (window.__mdSnifferInstalled) return;
  window.__mdSnifferInstalled = true;
  const ext = typeof browser !== "undefined" ? browser : chrome;
  const found = new Map();

  const MEDIA_EXT =
    /\.(m3u8|mpd|mp4|m4v|flv|webm|m4a|mp3|aac|ogg|ts|m4s|mov|mkv)(\?|#|$)/i;
  const HLS_TXT =
    /\/(master|index|playlist)[^/]*\.(txt|m3u)(\?|#|$)|\/hls\d?\/|\.urlset/i;
  const CDN =
    /bilivideo|upos-|googlevideo|douyinvod|bytefcdn|xhscdn|tiktokcdn|cloudfront|akamai|\/hls\/|\/hls3\/|playlist\.m3u8|index\.m3u8|master\.txt|\.ts\?|videoplayback|playurl|get_video/i;

  function isBlocked(url) {
    if (!url || typeof url !== "string") return true;
    if (!(url.startsWith("http://") || url.startsWith("https://"))) return true;
    if (url.length > 4000) return true;
    const low = url.toLowerCase();
    if (low.includes("data.bilibili.com/log") || low.includes("/log/web")) return true;
    if (low.includes("pbp/data") || low.includes("mountaintoys")) return true;
    if (/\.(js|css|png|jpe?g|gif|svg|woff2?|ico|webp)(\?|#|$)/i.test(low)) return true;
    return false;
  }

  function keep(url) {
    if (isBlocked(url)) return false;
    return MEDIA_EXT.test(url) || HLS_TXT.test(url) || CDN.test(url);
  }

  function guessKind(url) {
    const u = (url || "").toLowerCase();
    if (
      /\.m3u8(\?|#|$)/.test(u) ||
      u.includes("mpegurl") ||
      /\/(master|index|playlist)[^/]*\.(txt|m3u)(\?|#|$)/.test(u) ||
      (u.includes("/hls") && (u.includes(".urlset") || u.endsWith(".txt")))
    )
      return "hls";
    if (/\.mpd(\?|#|$)/.test(u)) return "dash";
    if (/30280|30002/.test(u) || /\.(mp3|m4a|aac)(\?|#|$)/.test(u)) return "audio";
    if (/\.ts(\?|#|$)/.test(u)) return "ts";
    if (/\.m4s(\?|#|$)/.test(u)) return "video";
    return "video";
  }

  function add(url, kind) {
    if (!keep(url)) return;
    url = String(url).split("#")[0];
    if (found.has(url)) return;
    found.set(url, { url: url, kind: kind || guessKind(url) });
    try {
      ext.runtime.sendMessage({
        type: "pageMedia",
        items: [{ url: url, kind: kind || guessKind(url) }],
      });
    } catch (_) {}
  }

  function pickUrl(input) {
    if (!input) return null;
    if (typeof input === "string") return input;
    try {
      if (input.url) return String(input.url);
      if (input.href) return String(input.href);
    } catch (_) {}
    return null;
  }

  // fetch
  try {
    const rawFetch = window.fetch;
    if (typeof rawFetch === "function") {
      window.fetch = function () {
        try {
          const u = pickUrl(arguments[0]);
          if (u) add(u);
        } catch (_) {}
        return rawFetch.apply(this, arguments).then(function (res) {
          try {
            if (res && res.url) add(res.url);
          } catch (_) {}
          return res;
        });
      };
    }
  } catch (_) {}

  // XHR
  try {
    const open = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function (method, url) {
      try {
        if (url) add(String(url));
      } catch (_) {}
      return open.apply(this, arguments);
    };
  } catch (_) {}

  // PerformanceObserver 持续监听资源
  function scanPerf() {
    try {
      const entries = performance.getEntriesByType("resource") || [];
      for (let i = 0; i < entries.length; i++) add(entries[i].name);
    } catch (_) {}
  }

  try {
    if (typeof PerformanceObserver !== "undefined") {
      const po = new PerformanceObserver(function (list) {
        list.getEntries().forEach(function (e) {
          add(e.name);
        });
      });
      po.observe({ entryTypes: ["resource"] });
    }
  } catch (_) {}

  function scanDom() {
    try {
      document.querySelectorAll("video, audio, source").forEach(function (el) {
        const src =
          el.currentSrc ||
          el.src ||
          el.getAttribute("src") ||
          el.getAttribute("data-src") ||
          el.getAttribute("data-url");
        if (src && !String(src).startsWith("blob:")) add(src, el.tagName === "AUDIO" ? "audio" : "video");
        // 部分播放器把地址放在 data-* 上
        ["data-src", "data-url", "data-video", "data-stream", "data-file"].forEach(function (attr) {
          const v = el.getAttribute(attr);
          if (v) add(v);
        });
      });
    } catch (_) {}
  }

  function scanScripts() {
    try {
      const re =
        /https?:\/\/[^\s"'\\<>]{8,500}?\.(?:m3u8|mpd|mp4|m4v|flv|webm|m4a|ts|m4s)(?:\?[^\s"'\\<>]*)?/gi;
      const nodes = document.querySelectorAll("script");
      for (let i = 0; i < nodes.length; i++) {
        const t = nodes[i].textContent || "";
        if (t.length < 20 || t.length > 800000) continue;
        let m;
        while ((m = re.exec(t))) add(m[0]);
      }
    } catch (_) {}
  }

  function collectAll() {
    scanPerf();
    scanDom();
    scanScripts();
    return Array.from(found.values());
  }

  try {
    ext.runtime.onMessage.addListener(function (msg, _s, sendResponse) {
      if (msg && msg.type === "scanPage") {
        const items = collectAll();
        try {
          ext.runtime.sendMessage({ type: "pageMedia", items: items });
        } catch (_) {}
        sendResponse({ items: items });
        return true;
      }
      return false;
    });
  } catch (_) {}

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", collectAll);
  } else {
    collectAll();
  }
  setInterval(scanPerf, 2000);
  setInterval(scanDom, 3000);

  // —— 浮层「下载此媒体」（对齐 GD4B）——
  var API_CANDIDATES = ["http://127.0.0.1:8765", "http://localhost:8765"];
  var pairedApi = null;

  function probeApi(cb) {
    var i = 0;
    function next() {
      if (i >= API_CANDIDATES.length) {
        cb(null);
        return;
      }
      var base = API_CANDIDATES[i++];
      fetch(base + "/api/status", { method: "GET", mode: "cors" })
        .then(function (r) {
          if (r.ok) {
            pairedApi = base;
            cb(base);
          } else next();
        })
        .catch(next);
    }
    next();
  }

  function ensureFloatBtn() {
    if (document.getElementById("md-float-dl")) return;
    var btn = document.createElement("div");
    btn.id = "md-float-dl";
    btn.textContent = "⬇ 下载此媒体";
    btn.title = "发送当前视频到 MediaDownloader";
    btn.style.cssText =
      "position:fixed;right:16px;bottom:80px;z-index:2147483646;padding:10px 14px;" +
      "background:#2563eb;color:#fff;border-radius:10px;font:13px/1.2 system-ui,sans-serif;" +
      "cursor:pointer;box-shadow:0 4px 14px rgba(0,0,0,.25);user-select:none;";
    btn.onmouseenter = function () {
      btn.style.background = "#1d4ed8";
    };
    btn.onmouseleave = function () {
      btn.style.background = "#2563eb";
    };
    btn.onclick = function () {
      var items = collectAll();
      var best =
        items.find(function (x) {
          return x.kind === "hls" || x.kind === "dash";
        }) ||
        items.find(function (x) {
          return x.kind === "video";
        }) ||
        items[0];
      var v = document.querySelector("video");
      var src = best && best.url;
      if (!src && v) {
        src = v.currentSrc || v.src;
        if ((!src || src.startsWith("blob:")) && v.querySelector("source")) {
          var s = v.querySelector("source");
          if (s && s.src) src = s.src;
        }
      }
      if (!src || src.startsWith("blob:")) {
        btn.textContent = "请先播放再试";
        setTimeout(function () {
          btn.textContent = "⬇ 下载此媒体";
        }, 2000);
        return;
      }
      btn.textContent = "发送中…";
      var send = function (api) {
        if (!api) {
          btn.textContent = "本机未启动";
          setTimeout(function () {
            btn.textContent = "⬇ 下载此媒体";
          }, 2500);
          return;
        }
        var isHls = /\.m3u8|\/hls|\.mpd|master\.txt/i.test(src);
        fetch(api + "/api/sniff/download", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            urls: [src],
            options: {
              use_hls_engine: isHls,
              queue_name: "sniff",
              direct_cdn: !isHls,
            },
          }),
        })
          .then(function (r) {
            return r.json();
          })
          .then(function () {
            btn.textContent = "已发送 ✓";
            setTimeout(function () {
              btn.textContent = "⬇ 下载此媒体";
            }, 2000);
          })
          .catch(function () {
            btn.textContent = "发送失败";
            setTimeout(function () {
              btn.textContent = "⬇ 下载此媒体";
            }, 2000);
          });
      };
      if (pairedApi) send(pairedApi);
      else probeApi(send);
    };
    try {
      document.documentElement.appendChild(btn);
    } catch (_) {}
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", ensureFloatBtn);
  } else {
    ensureFloatBtn();
  }
  setTimeout(ensureFloatBtn, 1500);
  probeApi(function () {});

})();
