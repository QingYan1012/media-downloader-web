/* 界面多语言（zh / en）的词表与切换。
 *
 * 口径：只翻界面。后端话术（HTTPException 的 detail、运行日志正文、订阅规则摘要）一个字不翻 ——
 * 那些是历史记录与 59 套自检断言的对象，翻了就等于篡改落盘的记录，且会把断言大面积打红。
 * 前端自己写的报错（friendlyError 那 22 条分支）排在后面一批，原因写在词表下面那段注释里。
 *
 * zh 的词表值必须与改前模板里硬编码的那句一字不差，否则中文用户看到的界面就被我改动了。
 * 键的完整性由 tests/i18n_test.py 盯：模板里用到的每个键都要在词表里、zh 与 en 的键集合要一致、
 * 同一个键两边的 {n} 占位符要对得上 —— 不靠人记。
 */
(function (global) {
  const DICT = {
    zh: {
      'doc.title': '多媒体下载器',
      brand: '多媒体下载器',
      'navGroup.download': '下载',
      'navGroup.fetch': '获取与处理',
      'navGroup.library': '媒体库',
      'navGroup.auto': '自动化',
      'navGroup.system': '系统',
      'navGroup.other': '其他',
      'nav.home': '下载解析', 'nav.queue': '队列', 'nav.bt': '磁力 / 种子', 'nav.info': '信息',
      'nav.search': '搜索', 'nav.music': '音乐', 'nav.tg': 'TG 频道', 'nav.voice': '语音',
      'nav.favs': '收藏', 'nav.live': '直播', 'nav.library': '资源库', 'nav.files': '文件',
      'nav.history': '历史', 'nav.log': '日志', 'nav.sniff': '嗅探', 'nav.subs': '订阅',
      'nav.settings': '设置',
      'page.home': '下载解析', 'page.sniff': '网页嗅探', 'page.queue': '下载队列',
      'page.bt': '磁力 / 种子', 'page.info': '媒体信息', 'page.search': '聚合搜索',
      'page.music': '音乐搜索', 'page.tg': 'Telegram 频道批量', 'page.voice': '语音工具',
      'page.subs': '订阅追踪', 'page.favs': '收藏关注', 'page.live': '直播录制',
      'page.library': '资源库', 'page.files': '文件浏览', 'page.history': '历史记录',
      'page.log': '运行日志', 'page.settings': '设置',
      'header.active': '进行中 {n}', 'header.activeTip': '队列中未完成的任务数',
      'header.failed': '失败 {n}', 'header.failedTip': '本轮失败任务数',
      'header.subNew': '订阅新增 {n}', 'header.subNewTip': '订阅已检测到但尚未下载的新条目数',
      'header.themeGroup': '主题色', 'header.toLight': '切换为浅色', 'header.toDark': '切换为深色',
      'header.langGroup': '界面语言',
      'header.langTip': '界面语言只改界面文字：后端返回的报错正文与运行日志仍是中文',
    },
    en: {
      'doc.title': 'Media Downloader',
      brand: 'Media Downloader',
      'navGroup.download': 'Download',
      'navGroup.fetch': 'Fetch & Process',
      'navGroup.library': 'Media Library',
      'navGroup.auto': 'Automation',
      'navGroup.system': 'System',
      'navGroup.other': 'Other',
      'nav.home': 'Parse', 'nav.queue': 'Queue', 'nav.bt': 'Torrents', 'nav.info': 'Details',
      'nav.search': 'Search', 'nav.music': 'Music', 'nav.tg': 'TG Channels', 'nav.voice': 'Voice',
      'nav.favs': 'Favorites', 'nav.live': 'Live', 'nav.library': 'Library', 'nav.files': 'Files',
      'nav.history': 'History', 'nav.log': 'Log', 'nav.sniff': 'Sniffer', 'nav.subs': 'Subscriptions',
      'nav.settings': 'Settings',
      'page.home': 'Link parsing', 'page.sniff': 'Page sniffer', 'page.queue': 'Download queue',
      'page.bt': 'Torrents & magnets', 'page.info': 'Media info', 'page.search': 'Aggregated search',
      'page.music': 'Music search', 'page.tg': 'Telegram channel batch', 'page.voice': 'Voice tools',
      'page.subs': 'Subscriptions', 'page.favs': 'Favorites & follows', 'page.live': 'Live recording',
      'page.library': 'Media library', 'page.files': 'File browser', 'page.history': 'History',
      'page.log': 'Runtime log', 'page.settings': 'Settings',
      'header.active': 'Running {n}', 'header.activeTip': 'Tasks still in the queue',
      'header.failed': 'Failed {n}', 'header.failedTip': 'Failed tasks in this round',
      'header.subNew': 'New {n}', 'header.subNewTip': 'New subscription items found but not downloaded yet',
      'header.themeGroup': 'Accent colour', 'header.toLight': 'Switch to light', 'header.toDark': 'Switch to dark',
      'header.langGroup': 'Interface language',
      'header.langTip': 'This only changes the interface text: backend error messages and the runtime log stay Chinese',
    },
  };

  // friendlyError 那 22 条报错分支的英文对照排在这一批之后：那些话术里点名着
  // 「设置 → 网络与并发」这类界面路径，路径本身还没翻，先翻错误只会让英文用户照着一句
  // 对不上按钮名的话去找设置项。届时每条分支带一个 code，en 查不到就退回中文原话。

  const UI_LANGS = [
    { key: 'auto', label: 'AUTO', name: { zh: '自动（跟随浏览器）', en: 'Auto (follow browser)' } },
    { key: 'zh', label: '中', name: { zh: '中文', en: '简体中文' } },
    { key: 'en', label: 'EN', name: { zh: '英文', en: 'English' } },
  ];

  function detect(pref) {
    if (pref === 'zh' || pref === 'en') return pref;
    const nav = String((global.navigator && global.navigator.language) || 'zh');
    return nav.toLowerCase().indexOf('zh') === 0 ? 'zh' : 'en';
  }

  const I18N = {
    lang: detect('auto'),
    pref: 'auto',
    langs: UI_LANGS,
    t(key, vars, lang) {
      const L = lang || I18N.lang;
      const raw = (DICT[L] && DICT[L][key] != null) ? DICT[L][key]
        : (DICT.zh[key] != null ? DICT.zh[key] : key);
      if (!vars) return raw;
      return String(raw).replace(/\{(\w+)\}/g, (m, k) => (vars[k] != null ? String(vars[k]) : m));
    },
    apply(pref) {
      I18N.pref = pref === 'zh' || pref === 'en' ? pref : 'auto';
      I18N.lang = detect(I18N.pref);
      try {
        global.localStorage.setItem('md_lang', I18N.pref);
        // 刷新生效时用的镜像：/api/status 回来之前先按这个显示，免得整页闪一下语言
        global.localStorage.setItem('md_lang_resolved', I18N.lang);
      } catch (_) {}
      const el = global.document.documentElement;
      el.setAttribute('lang', I18N.lang === 'zh' ? 'zh-CN' : 'en');
      global.document.title = I18N.t('doc.title');
      return I18N.lang;
    },
    boot() {   // 页面刚进来、还没拿到后端设置时：用上次刷新生效留下的那份镜像
      let mirror = '';
      try { mirror = global.localStorage.getItem('md_lang_resolved') || ''; } catch (_) {}
      return I18N.apply(mirror === 'en' ? 'en' : (mirror === 'zh' ? 'zh' : 'auto'));
    },
    // 传 lang 而不是读 I18N.lang：界面那侧要用 computed 包一层，必须从参数拿到语言才能被 uiLang 触发重算
    elementLocale(lang) {
      if ((lang || I18N.lang) === 'en' && global.ElementPlusLocaleEn) return global.ElementPlusLocaleEn;
      return global.ElementPlusLocaleZhCn;   // en 的词包没加载上就退回中文，别把控件的 locale 传成 undefined
    },
  };

  global.MD_I18N = I18N;
  global.MD_I18N_DICT = DICT;
})(window);
