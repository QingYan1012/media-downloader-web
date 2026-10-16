
    const { createApp, ref, reactive, computed, onMounted, onUnmounted, watch, nextTick } = Vue;

    createApp({
      setup() {
        const page = ref('home');
        const navs = [
          { key: 'home', label: '下载解析', icon: 'download' },
          { key: 'queue', label: '队列', icon: 'list-ordered' },
          { key: 'bt', label: '磁力 / 种子', icon: 'magnet' },
          { key: 'info', label: '信息', icon: 'info' },
          { key: 'search', label: '搜索', icon: 'search' },
          { key: 'music', label: '音乐', icon: 'music' },
          { key: 'tg', label: 'TG 频道', icon: 'send' },
          { key: 'voice', label: '语音', icon: 'mic' },
          { key: 'favs', label: '收藏', icon: 'star' },
          { key: 'live', label: '直播', icon: 'radio' },
          { key: 'library', label: '资源库', icon: 'library' },
          { key: 'files', label: '文件', icon: 'folder' },
          { key: 'history', label: '历史', icon: 'history' },
          { key: 'log', label: '日志', icon: 'scroll-text' },
          { key: 'sniff', label: '嗅探', icon: 'radar' },
          { key: 'subs', label: '订阅', icon: 'bell' },
          { key: 'settings', label: '设置', icon: 'settings' },
        ];
        const NAV_GROUPS = [
          { title: '下载', keys: ['home', 'queue', 'bt', 'sniff', 'info'] },
          { title: '获取与处理', keys: ['search', 'music', 'tg', 'live', 'voice'] },
          { title: '媒体库', keys: ['library', 'files', 'favs', 'history'] },
          { title: '自动化', keys: ['subs'] },
          { title: '系统', keys: ['log', 'settings'] },
        ];
        /* 鸣谢名单：新增依赖或参考项目时在这里补一行（url 留空则只显示名字） */
        const CREDITS = [
          {
            title: '引擎与依赖',
            items: [
              { name: 'yt-dlp', url: 'https://github.com/yt-dlp/yt-dlp', note: '主力解析与下载引擎，支持上千站点' },
              { name: 'N_m3u8DL-RE', url: 'https://github.com/nilaoda/N_m3u8DL-RE', note: 'm3u8 / DASH 流媒体分段下载' },
              { name: 'FFmpeg', url: 'https://ffmpeg.org', note: '合流、转码、字幕内嵌、校验文件可播放性' },
              { name: 'FFmpeg-Builds (BtbN)', url: 'https://github.com/BtbN/FFmpeg-Builds', note: 'Windows 一键更新的构建来源' },
              { name: 'aria2', url: 'https://github.com/aria2/aria2', note: '可选后端：大文件分片加速，以及「磁力 / 种子」那一页的下载与做种都交给它（需自备 aria2c）' },
              { name: 'faster-whisper', url: 'https://github.com/SYSTRAN/faster-whisper', note: '本地语音转写，无需联网' },
              { name: 'Demucs', url: 'https://github.com/facebookresearch/demucs', note: '人声 / 伴奏分离' },
              { name: 'edge-tts', url: 'https://github.com/rany2/edge-tts', note: '字幕配音，生成语音' },
              { name: 'deep-translator', url: 'https://github.com/nidhaloff/deep-translator', note: '字幕机翻' },
              { name: 'musicdl', url: 'https://github.com/CharlesPikachu/musicdl', note: '跨平台按曲名获取音乐下载地址' },
              { name: 'mutagen', url: 'https://github.com/quodlibet/mutagen', note: '写入音频文件的封面与标签' },
              { name: 'Telethon', url: 'https://github.com/LonamiWebs/Telethon', note: 'Telegram 用户会话，列出并下载账号可访问的频道' },
              { name: 'Chromaprint / fpcalc', url: 'https://github.com/acoustid/chromaprint', note: '本机生成声学指纹' },
              { name: 'AcoustID', url: 'https://acoustid.org', note: '按指纹反查曲目' },
              { name: 'MusicBrainz', url: 'https://musicbrainz.org', note: '曲目元数据来源' },
              { name: 'Cover Art Archive', url: 'https://coverartarchive.org', note: '专辑封面图片来源' },
              { name: 'SponsorBlock', url: 'https://sponsor.ajay.app', note: '标记视频中的广告片段' },
              { name: 'FastAPI', url: 'https://github.com/fastapi/fastapi', note: '本地后端服务' },
              { name: 'Vue', url: 'https://vuejs.org', note: '前端框架' },
              { name: 'Element Plus', url: 'https://element-plus.org', note: '按钮、输入框等控件' },
              { name: 'lucide', url: 'https://lucide.dev', note: '侧栏与操作图标' },
            ]
          },
          {
            title: '界面与功能参考',
            items: [
              { name: 'Ghost-Downloader-3', url: 'https://github.com/XiaoYouChR/Ghost-Downloader-3', note: '下载队列、并发与状态展示的实现方式' },
              { name: 'voice-pro', url: 'https://github.com/abus-aikorea/voice-pro', note: '人声分离、字幕配音、准实时转写翻译' },
              { name: 'AI-Video-Transcriber', url: 'https://github.com/wendy7756/AI-Video-Transcriber', note: '字幕优先的转写流水线思路' },
              { name: 'MediaSync', url: 'https://github.com/lincolnpark2000/MediaSync', note: '文件浏览、下载归档与跳过已下载' },
              { name: 'XiaDown（下蛋）', url: 'https://xiadown.app/', note: '接管 Chrome 监听页面加载的媒体进行嗅探' },
              { name: 'cat-catch（猫抓）', url: 'https://github.com/xifangczy/cat-catch', note: 'GPL-3.0 资源嗅探扩展；本工具做它的「发送数据」接收端与正则规则导入，仅按公开配置格式对接，未复制代码' },
              { name: 'GD4B', url: '', note: '浏览器嗅探扩展的同类实现' },
              { name: 'spotDL', url: 'https://github.com/spotdl/spotDL', note: '同曲判定的打分闸门（曲名、歌手、时长各自评分后合并）思路参考，未复制代码' },
              { name: 'Emby', url: 'https://emby.media', note: '音乐库按目录读曲（/{专辑}/{年份}/{序号} - {曲名}）的口径参考，未复制代码' },
              { name: 'Jellyfin', url: 'https://jellyfin.org', note: '同上：命名模板里 {track} {disc} {year} {date} 的排法参考它的读库习惯，未复制代码' },
              { name: 'go-music-dl', url: 'https://github.com/guohuiyuan/go-music-dl', note: '跨平台按曲名匹配、歌单转链取址的功能思路参考（AGPL 项目，未复制代码）' },
              { name: 'simple_sq_music_plus', url: 'https://github.com/59799517/simple_sq_music_plus', note: '歌单追新与自建收藏清单的功能思路参考（未复制代码）' },
              { name: 'flacdownloader.com', url: 'https://flacdownloader.com', note: 'Qobuz / Tidal 无损参照元数据（曲名、ISRC、是否无损）来源' },
              { name: 'qBittorrent Enhanced Edition', url: 'https://github.com/c0re100/qBittorrent-Enhanced-Edition', note: 'GPL-3.0；磁力 / 种子的 tracker 自动更新、做种与限速这些功能照着它的产品形态设计，未复制任何代码，tracker 列表也不写死在源码里而是运行时按 URL 抓取' },
            ]
          },
          {
            title: 'Tracker 列表来源',
            items: [
              { name: 'ngosang/trackerslist', url: 'https://github.com/ngosang/trackerslist', note: '公开维护的 BitTorrent announce 列表；本工具只在设置里存它的地址，正文每次现抓，不落进发布包' },
              { name: 'XIU2/TrackersListCollection', url: 'https://github.com/XIU2/TrackersListCollection', note: '同上，第二个默认来源；抓回来的清单只存本机 torrent_state/ 下' },
            ]
          }
        ];
        const navGroups = computed(() => {
          const byKey = new Map(navs.map((n) => [n.key, n]));
          const used = new Set();
          const gs = NAV_GROUPS.map((g) => ({
            title: g.title,
            items: g.keys.filter((k) => byKey.has(k)).map((k) => { used.add(k); return byKey.get(k); }),
          })).filter((g) => g.items.length);
          const rest = navs.filter((n) => !used.has(n.key));
          if (rest.length) gs.push({ title: '其他', items: rest });
          return gs;
        });
        const appVersion = 'v1.3.2 · Element Plus';
        const pageTitle = computed(() => {
          const m = { home: '下载解析', sniff: '网页嗅探', queue: '下载队列', bt: '磁力 / 种子', info: '媒体信息', search: '聚合搜索', music: '音乐搜索', tg: 'Telegram 频道批量', voice: '语音工具', subs: '订阅追踪', favs: '收藏关注', live: '直播录制', library: '资源库', files: '文件浏览', history: '历史记录', log: '运行日志', settings: '设置' };
          return m[page.value] || '';
        });
        const queueStat = computed(() => {
          const list = tasks.value || [];
          let active = 0, failed = 0;
          for (const t of list) {
            if (t.status === 'failed') failed++;
            else if (t.status !== 'finished') active++;
          }
          return { active, failed };
        });
        // 磁力 / 种子任务自成「磁力 / 种子」页，队列页只看其余任务
        const btTasks = computed(() => (tasks.value || []).filter(t => t.kind === 'torrent'));
        const queueTasks = computed(() => (tasks.value || []).filter(t => t.kind !== 'torrent'));
        // 封面拉不到（防盗链、地址过期）时按任务号记住，不给卡片留一个破图框
        const thumbBroken = reactive({});
        // 全选 / 批量操作只作用在当前页看得见的那些任务，不能把另一页的任务悄悄删掉
        const visibleTasks = computed(() => page.value === 'bt' ? btTasks.value : queueTasks.value);
        function activeOf(list) {
          return (list || []).filter(t => t.status !== 'finished' && t.status !== 'failed').length;
        }
        const subNewTotal = computed(() => (subs.value || []).reduce((a, s) => a + (s.new_count || 0), 0));
        function navBadge(k) {
          if (k === 'queue') return activeOf(queueTasks.value) || '';
          if (k === 'bt') return activeOf(btTasks.value) || '';
          if (k === 'subs') return subNewTotal.value || '';
          return '';
        }

        const urlText = ref('');
        const opts = ref({
          video_quality: 'best',
          audio_quality: 'best',
          format: 'mkv',
          download_dir: '',
          embed_sub: true,
          audio_only: false,
          download_danmaku: true,
          embed_thumb: true,
          embed_meta: true,
          embed_chapters: true,
          local_ai_transcribe: false,
          local_ai_translate: false,
          local_ai_lang: 'auto',
          whisper_model: 'base',
          whisper_device: 'auto',
          whisper_compute: 'auto',
          skip_downloaded: true,
          verify_download: true,
          allow_playlist: false,
          playlist_start: 0,
          playlist_end: 0,
          playlist_items: '',
          sponsorblock: 'off',
          prefer_codec: 'auto',
          write_sub_files: true,
          subtitle_langs: 'zh-Hans,zh-CN,zh,zh-Hant,zh-TW',
          download_section: '',
          download_later: false,
          use_hls_engine: false,
          force_format: '',
          ytdlp_extra_args: '',
          is_live: false,
        });
        const videoQualities = ['best', '4K', '1440p', '1080p', '720p', '480p', '360p'];
        const audioQualities = ['best', '320k', '256k', '192k', '128k'];
        const formats = ['mkv', 'mp4', 'webm', 'mp3', 'm4a', 'flac'];
        const codecOptions = [
          { label: '自动', value: 'auto' },
          { label: 'H.264', value: 'avc' },
          { label: 'VP9', value: 'vp9' },
          { label: 'AV1', value: 'av1' },
        ];
        const selectedIds = ref([]);
        const selectAll = ref(false);
        const queuePaused = ref(false);
        const taskSort = ref('queue');

        // 字幕多选：任意组合，不限定双语
        const subLangOptions = [
          { label: '简体中文 (zh-Hans)', value: 'zh-Hans' },
          { label: '简体中文 (zh-CN)', value: 'zh-CN' },
          { label: '中文 (zh)', value: 'zh' },
          { label: '繁体中文 (zh-Hant)', value: 'zh-Hant' },
          { label: '繁体中文 (zh-TW)', value: 'zh-TW' },
          { label: '英语 (en)', value: 'en' },
          { label: '日语 (ja)', value: 'ja' },
          { label: '韩语 (ko)', value: 'ko' },
          { label: '法语 (fr)', value: 'fr' },
          { label: '德语 (de)', value: 'de' },
          { label: '西班牙语 (es)', value: 'es' },
          { label: '俄语 (ru)', value: 'ru' },
          { label: '葡萄牙语 (pt)', value: 'pt' },
          { label: '意大利语 (it)', value: 'it' },
          { label: '越南语 (vi)', value: 'vi' },
          { label: '泰语 (th)', value: 'th' },
          { label: '印尼语 (id)', value: 'id' },
          { label: '阿拉伯语 (ar)', value: 'ar' },
          { label: '印地语 (hi)', value: 'hi' },
        ];
        const subLangList = ref(['zh-Hans', 'zh-CN', 'zh', 'zh-Hant', 'zh-TW']);
        function selectAllSubLangs() {
          subLangList.value = subLangOptions.map(i => i.value);
        }
        function clearSubLangs() {
          subLangList.value = [];
        }
        function toggleSubLang(val) {
          const i = subLangList.value.indexOf(val);
          if (i >= 0) subLangList.value.splice(i, 1);
          else subLangList.value.push(val);
        }
        function syncSubLangsToOpts() {
          opts.value.subtitle_langs = subLangList.value.length
            ? subLangList.value.join(',')
            : 'zh-Hans,zh,en';
        }

        const status = ref({ ffmpeg: '-', ytdlp: '-', running: 0, ffmpeg_path: '', cookie_source: 'none' });
        const tasks = ref([]);
        const mediaInfo = ref(null);
        const selectedQuality = ref('');
        // 解析页的画面编码筛选：'' = 全部，其余取 _resolve_format 认的 prefer_codec 值
        const infoCodec = ref('');
        // 区间勾选要拿行对象本体去调 el-table，所以留一个表格 ref
        const entryTableRef = ref(null);
        const entrySel = ref([]);
        const entryRange = ref({ from: 1, to: 1 });
        const fileItems = ref([]);
        const filesPath = ref('');
        const filesRoot = ref('');
        const batchMode = ref('transcribe');
        const batchScope = ref('folder');
        const batchRunning = ref(false);
        const selectedFiles = ref([]);
        const syncOffsetSec = ref(0);
        const syncScale = ref(1);
        const syncInplace = ref(false);
        const history = ref([]);
        const histStats = ref({ total: 0, success: 0, failed: 0, success_rate: '0%' });
        const histSearch = ref('');
        const logs = ref([]);
        const logLevel = ref('all');
        const logSearch = ref('');
        const logLoc = ref({ dir: '', file: 'app.log', archives: [] });
        const settings = ref({
          proxy: '',
          proxy_mode: 'auto',
          proxy_by_platform: {},
          nocheckcertificate: true,
          concurrent: 3,
          download_dir: '',
          cookie_source: 'none',
          cookie_browser: 'chrome',
          cookie_file: '',
          ffmpeg_path: '',
          video_encoder: 'cpu',
          video_cpu_codec: 'x264',
          video_cpu_preset: 'medium',
          // 访问保护（登录）：默认关，读数由 loadConfig 从 /api/config 覆盖
          web_auth_enabled: false,
          web_auth_session_hours: 12,
          web_auth_remember_days: 30,
          web_auth_max_fails: 5,
          web_auth_lock_minutes: 15,
          speed_limit: '',
          global_speed_limit: '',
          speed_windows: '',
          run_window: '',
          queue_windows: {},
          ytdlp_extra_args: '',
          max_per_host: 2,
          adaptive_throttle: true,
          plugins_enabled: true,
          aria2_enabled: false,
          aria2_rpc: 'http://127.0.0.1:6800/jsonrpc',
          aria2_secret: '',
          aria2_for_large_mb: 50,
          aria2_bin: '',
          aria2_autostart: true,
          torrent_seed_ratio: 1.0,
          torrent_seed_time: 3600,
          torrent_meta_timeout: 180,
          bt_trackers: '',
          bt_tracker_sources: '',
          bt_tracker_auto_update: true,
          bt_tracker_max: 30,
          bt_dl_limit: '',
          bt_ul_limit: '',
          bt_prioritize_piece: false,
          bt_auto_rules: [],
          bt_auto_fallback: '',
          http_impersonate: true,
          yt_player_clients: 'default,web_safari,tv,android,ios',
          po_provider_enabled: false,
          po_provider_url: 'http://127.0.0.1:4416',
          github_mirror: 'https://ghproxy.net/',
          pip_mirror: 'https://pypi.tuna.tsinghua.edu.cn/simple',
          components_auto_check: true,
          sub_first_download_n: 0,
          local_ai_transcribe: false,
          local_ai_translate: false,
          local_ai_lang: 'auto',
          whisper_model: 'base',
          whisper_device: 'auto',
          whisper_compute: 'auto',
          diarization_enabled: false,
          diarization_max_speakers: 4,
          hf_token: '',
          local_ai_mt_after_transcribe: false,
          subtitle_first: true,
          ai_polish: false,
          ai_summarize: false,
          summary_lang: 'zh',
          translate_auto_fallback: true,
          edge_tts_voice: 'zh-CN-XiaoxiaoNeural',
          demucs_model: 'htdemucs',
          subtitle_translate_provider: 'deepl',
          subtitle_target_lang: 'zh',
          subtitle_glossary: '',
          subtitle_wrap: true,
          subtitle_wrap_width: 16,
          subtitle_wrap_lines: 3,
          subtitle_qc: true,
          subtitle_qc_reflect: false,
          subtitle_export_set: 'single',
          deepl_api_key: '',
          deepl_api_url: '',
          openai_api_key: '',
          acoustid_api_key: '',
          openai_base_url: 'https://api.openai.com/v1',
          openai_model: 'gpt-4o-mini',
          anthropic_api_key: '',
          anthropic_model: 'claude-sonnet-4-20250514',
          gemini_api_key: '',
          gemini_model: 'gemini-2.0-flash',
          google_translate_api_key: '',
          azure_translator_key: '',
          azure_translator_region: 'eastasia',
          azure_translator_endpoint: 'https://api.cognitive.microsofttranslator.com',
          filename_template: '%(title).80B [%(id)s].%(ext)s',
          write_description: false,
          write_info_json: false,
          write_sub_files: true,
          dark_mode: false,
          ui_theme: 'blue',
          telegram_enabled: false,
          telegram_bot_token: '',
          telegram_chat_id: '',
          telegram_notify_done: true,
          telegram_notify_fail: true,
          telegram_notify_sub: true,
          telegram_commands_enabled: true,
          sub_interval_min: 60,
          sub_auto_download: true,
          live_from_start: true,
          live_max_minutes: 0,
          live_stream_fallback: true,
          live_stream_pref_bilibili: 'flv',
          live_stream_pref_youtube: 'dash',
          live_stream_pref_douyin: 'hls',
          live_stream_pref_twitch: 'hls',
          live_stream_pref_default: 'auto',
          serverchan_sendkey: '',
          wecom_enabled: false,
          wecom_corp_id: '',
          wecom_corp_secret: '',
          wecom_agent_id: '',
          wecom_touser: '@all',
          wecom_notify_done: true,
          wecom_notify_fail: true,
          wecom_notify_sub: false,
          storage_post_action: 'none',
          storage_nas_enabled: false,
          storage_nas_path: '',
          storage_webdav_enabled: false,
          storage_webdav_url: '',
          storage_webdav_user: '',
          storage_webdav_pass: '',
          storage_webdav_path: '/',
          risk_preset: 'standard',
          risk_delay_sec: 1,
          concurrent_fragments: 4,
          sub_scan_delay_sec: 10,
          risk_cooldown_429: 60,
          risk_user_agent: '',
        });
        const subs = ref([]);
        const subUrl = ref('');
        const subMode = ref('');
        const subAdding = ref(false);
        const subScanning = ref(false);
        const subBusy = ref('');
        const backfillSub = ref(null);
        const backfillRange = ref([]);
        const backfilling = ref(false);
        // 同步计划预览：干跑一轮的结论 + 上游删除留档清单，都按订阅逐条看
        const subPlanSub = ref(null);
        const subPlan = ref(null);
        const subPlanLoading = ref(false);
        const subPlanArch = ref([]);
        // 和后端 _sub_kind_of / _looks_like_feed 一个口径：Telegram 优先，再看 RSS 特征
        const RSS_HINTS = ['.rss', '.atom', '.xml', '/feed', '/rss', 'feed://'];
        // 音乐歌单的域名表由后端 /api/subs 下发（PLAYLIST_HOSTS 只有一份，抄两遍必然漂移）
        const subMusicHosts = ref([]);
        function isMusicPlaylistUrl(u) {
          const raw = (u || '').trim();
          if (!/^https?:\/\//i.test(raw)) return false;
          let host = '';
          try { host = new URL(raw).hostname.toLowerCase(); } catch (_) { return false; }
          const hit = (h) => host === h || host.endsWith('.' + h);
          // 抖音 / 汽水的域名也开歌单页，但同域名下绝大多数链接是单视频或主页
          if (hit('douyin.com') || hit('qishui.com')) {
            return /playlist|songlist|mix|collection|music\./i.test(raw);
          }
          return (subMusicHosts.value || []).some(hit);
        }
        // 只认 @开头 和 t.me 域内写法：裸单词（"youtube"）不当频道，免得建出一条报错订阅
        function subKindOfUrl(u) {
          const raw = (u || '').trim();
          if (raw.startsWith('@') || /(?:^|\/\/)(?:www\.)?(?:t|telegram)\.me\//i.test(raw)) return 'tg';
          if (RSS_HINTS.some((h) => raw.toLowerCase().includes(h))) return 'rss';
          if (isMusicPlaylistUrl(raw)) return 'music';
          return '';
        }
        const SUB_KIND_META = {
          tg: { label: 'Telegram', tagType: 'warning', hint: '公开频道可匿名读取历史；文件 / 音频帖和私有频道需使用账号会话。' },
          rss: { label: 'RSS', tagType: 'success', hint: '按订阅源里的条目链接或 enclosure 下载；播客音频按音频处理。' },
          music: { label: '音乐歌单', tagType: '', hint: '网易云 / QQ 音乐 / 酷狗 / Spotify 等平台的歌单链接：每轮只下歌单里新增的歌，命名与音质沿用音乐搜索页的设置。' },
          '': { label: '视频源', tagType: 'info', hint: 'YouTube / B站 / 抖音等，走 yt-dlp 解析频道、播放列表或单视频。' },
        };
        const subKindMeta = (k) => SUB_KIND_META[k || ''] || SUB_KIND_META[''];
        const subKindInfo = (u) => subKindMeta(subKindOfUrl(u));
        function subStatus(s) {
          if (subBusy.value === s.id) return { tone: 'busy', text: '检查中' };
          if (s.last_error) return { tone: 'bad', text: '读取失败' };
          if (!s.last_check) return { tone: '', text: '未扫描' };
          return { tone: 'ok', text: '已最新' };
        }
        // 一行一个源；也容忍一行里塞多个（按空格/逗号/分号切开）
        function subLines(text) {
          const out = [], seen = new Set();
          for (const piece of String(text || '').split(/[\s,，、;；]+/)) {
            const u = piece.trim().replace(/[)\]}>]+$/, '');
            if (!u || seen.has(u)) continue;
            const ok = /^https?:\/\//i.test(u) || u.startsWith('@')
              || /(?:^|\/\/)(?:www\.)?(?:t|telegram)\.me\//i.test(u);
            if (ok) { seen.add(u); out.push(u); }
          }
          return out;
        }
        const subFirst = computed(() => subLines(subUrl.value)[0] || '');
        const subAddCount = computed(() => subLines(subUrl.value).length);
        const subAutoAdd = ref(true);
        const subIsTg = computed(() => subKindOfUrl(subFirst.value) === 'tg');
        const liveUrl = ref('');
        // 录制时长：0 = 跟随「设置」里的默认最长录制时长，录满由后端收尾保存成品
        const liveRecordMinutes = ref(0);
        const liveDefaultMinutesText = computed(() => {
          const n = Number(settings.value.live_max_minutes || 0);
          return n > 0 ? `录满 ${n} 分钟自动保存` : '不限时长';
        });
        const liveMonitorUrl = ref('');
        const liveMonitors = ref([]);
        // 每房间录制口径：容器取视频可用的三种封装（与后端 _LIVE_FMTS 一致），画质沿用首页档位清单
        const liveRoomFmts = ['mkv', 'mp4', 'webm'];
        const liveRoomQualities = videoQualities;
        const liveRoomCfg = ref({
          visible: false, saving: false, id: '', url: '',
          fmt: '', video_quality: '', auto_transcode: '', max_minutes: 0, win_start: '', win_end: '',
        });
        const sniffUrl = ref('');
        const sniffLoading = ref(false);
        const sniffItems = ref([]);
        const sniffSelected = ref([]);
        const sniffDone = ref(false);
        const browserSniffPort = ref(9222);
        const browserSniffLoading = ref(false);
        const browserSniff = ref({
          running: false, status: 'idle', port: 9222, count: 0, items: [], tabs: [], error: '',
        });
        let browserSniffTimer = null;
        const sniffDisplayItems = computed(() => {
          const map = new Map();
          for (const it of (browserSniff.value.items || [])) {
            if (it && it.url) map.set(it.url, it);
          }
          for (const it of (sniffItems.value || [])) {
            if (it && it.url && !map.has(it.url)) map.set(it.url, it);
          }
          return Array.from(map.values());
        });
        const sniffMergeLoading = ref(false);
        const canSniffMerge = computed(() => {
          const selected = sniffDisplayItems.value.filter(it => sniffSelected.value.includes(it.url));
          const videos = selected.filter(it => ['video', 'hls', 'dash', 'direct'].includes((it.kind || '').toLowerCase()));
          const audios = selected.filter(it => (it.kind || '').toLowerCase() === 'audio');
          return videos.length === 1 && audios.length === 1;
        });
        const libraryItems = ref([]);
        const libraryLoading = ref(false);
        const libraryFilter = ref('all');
        const libraryFiltered = computed(() => {
          const f = libraryFilter.value;
          if (f === 'all') return libraryItems.value;
          return libraryItems.value.filter(x => x.kind === f);
        });
        const libSort = ref({ key: 'name', dir: 'asc', t: '资源库' });
        const LIB_DIR = { name: 'asc', kind: 'asc', res: 'desc', audio: 'desc', duration: 'desc', size: 'desc', mtime: 'desc' };
        const LIB_GETTERS = {
          name: x => x.name || '',
          kind: x => (x.kind || '') + '/' + (x.ext || ''),
          res: x => x.height || 0,
          audio: x => (x.lossless ? 1e12 : 0) + (x.bit_depth || 0) * 1e7 + (x.sample_rate || 0),
          duration: x => x.duration || 0,
          size: x => x.size || 0,
          mtime: x => x.mtime || ''
        };
        function libAudioText(it) {
          if (it.kind !== 'audio') return '-';
          const parts = [it.quality || it.ext || ''];
          if (it.bit_depth) parts.push(it.bit_depth + 'bit');
          if (it.sample_rate) parts.push((it.sample_rate / 1000).toFixed(1).replace(/\.0$/, '') + 'kHz');
          if (!it.bit_depth && it.bitrate_kbps) parts.push(it.bitrate_kbps + 'kbps');
          return parts.filter(Boolean).join(' ');
        }
        // 成品音质核对：后端逐份读成品自己的标签，前端只把结论挂回对应行（按 path 认，重新扫描后清空）
        const libQa = ref({});
        const libQaLoading = ref(false);
        const libQaSpec = ref('');
        const QA_TAGS = {
          low: { type: 'danger', text: '低于要求' },
          ok: { type: 'success', text: '符合' },
          unknown: { type: 'warning', text: '没核到' },
          missing: { type: 'danger', text: '文件不在' },
          none: { type: 'info', text: '未设要求' },
        };
        function libQaTag(it) {
          const r = libQa.value[it.path];
          const base = r && QA_TAGS[r.state];
          if (!base) return null;
          let tip = r.note || (r.state === 'ok' ? `已确认不低于「${libQaSpec.value || '本批要求'}」` : '');
          if (r.ref_note) tip += `｜与无损参照：${r.ref_note}`;
          return { type: base.type, text: base.text, tip };
        }
        const libQaAll = computed(() => Object.values(libQa.value));
        const libQaDone = computed(() => libQaAll.value.length);
        const qaCount = (st) => computed(() => libQaAll.value.filter(r => r.state === st).length);
        const libQaLow = qaCount('low');
        const libQaUnknown = qaCount('unknown');
        const libQaMissing = qaCount('missing');
        const libQaRefLow = computed(() => libQaAll.value.filter(r => r.ref_state === 'below').length);
        async function checkLibraryQuality() {
          const list = libraryFiltered.value.filter(x => x.kind === 'audio');
          if (!list.length) { ElementPlus.ElMessage.warning('当前列表里没有音频成品可核对'); return; }
          libQaLoading.value = true;
          try {
            const r = await api('/api/music/check_quality', {
              method: 'POST',
              body: JSON.stringify({ paths: list.map(x => x.path) }),
            });
            const map = { ...libQa.value };
            (r.rows || []).forEach(x => { map[x.path] = x; });
            libQa.value = map;
            libQaSpec.value = qualitySpecLabel(r.spec);
            const low = (r.below_spec || 0) + (r.below_reference || 0);
            if (low) ElementPlus.ElMessage.warning(`已核对 ${r.count} 份：${r.below_spec || 0} 份低于本批音质要求`
                                                   + (r.below_reference ? `，${r.below_reference} 份低于无损参照` : ''));
            else ElementPlus.ElMessage.success(`已核对 ${r.count} 份，没有低于本批音质要求（${libQaSpec.value || '未设'}）的成品`);
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '音质核对失败');
          } finally {
            libQaLoading.value = false;
          }
        }
        const librarySorted = computed(() => applySort(libraryFiltered.value, libSort.value, LIB_GETTERS));
        const transcodePresets = ref([]);

        const tgTesting = ref(false);
        const wecomTesting = ref(false);
        const storageTesting = ref(false);
        // 事件通知复选组：组级「已选/总数」与全选/半选按旗标清单现算，两个渠道共用
        const TG_DL_KEYS = ['telegram_notify_done', 'telegram_notify_fail'];
        const TG_CH_KEYS = ['telegram_notify_sub', 'telegram_commands_enabled'];
        const WECOM_DL_KEYS = ['wecom_notify_done', 'wecom_notify_fail'];
        const WECOM_CH_KEYS = ['wecom_notify_sub'];
        const flagCount = (keys) => keys.filter((k) => !!settings.value[k]).length;
        const flagAll = (keys) => flagCount(keys) === keys.length;
        const flagMixed = (keys) => flagCount(keys) > 0 && !flagAll(keys);
        function setFlags(keys, on) {
          keys.forEach((k) => { settings.value[k] = !!on; });
        }
        const riskPresets = ref({
          fast: { label: '快速' }, standard: { label: '标准' }, safe: { label: '安全' }, extreme: { label: '极端安全' }
        });
        const favTab = ref('folders');
        const favFolders = ref([]);
        const favFolderId = ref(null);
        const favItems = ref([]);
        const favSelected = ref([]);
        const favLoading = ref(false);
        const favMeta = ref({ total: 0, truncated: false, missing: 0 });
        const ytPlaylistUrl = ref('');
        const biliQrLoading = ref(false);
        const biliQrUrl = ref('');
        const biliQrKey = ref('');
        const biliQrMsg = ref('');
        const biliQrImage = ref('');
        const biliQrCanvas = ref(null);
        const musicCookieItems = ref([]);
        const musicCookieText = ref({});
        const ncQrLoading = ref(false);
        const ncQrUrl = ref('');
        const ncQrKey = ref('');
        const ncQrImage = ref('');
        const ncQrMsg = ref('');
        const playerUrl = ref('');
        const playerName = ref('');
        const playerIsVideo = ref(false);
        const playerIsAudio = ref(false);
        const mediaEl = ref(null);
        const transcriptBox = ref(null);
        const srtEditBox = ref(null);
        const transcript = ref({ srt: '', cues: [], message: '' });
        const mediaCueIdx = ref(-1);
        // 逐句校对台：rows 是本地副本，只有「保存」才写盘；mtimeTs 用于挡「读完之后字幕又被改写」
        const transcriptPath = ref('');
        const srtEdit = reactive({ on: false, busy: false, rows: [], srt: '', format: 'srt', mtimeTs: 0, sel: -1, dirty: false });
        // 质检读的是磁盘上的字幕，未保存的行内改动不在检查范围内
        const srtQc = reactive({ busy: false, rows: [], message: '', hint: '', paired: false, counter: '', lang: '', total: 0, wrap: { width: 16, lines: 3 }, reflect_on: false });
        const pipelineRow = ref(null);
        const pipelineView = ref(null);
        let pipelineTimer = null;
        const searchQuery = ref('');
        const installingVoice = ref(false);
        const voiceStatusText = ref('');
        const rtRecording = ref(false);
        const rtTranslate = ref(true);
        const rtTargetLang = ref('zh');
        const rtLog = ref('');
        let _rtMedia = null;
        let _rtRecorder = null;
        let _rtTimer = null;
        const musicKeyword = ref('');
        const musicResults = ref([]);
        const musicSearching = ref(false);
        const musicdlVersion = ref('');
        const musicdlReady = ref(false);
        const installingMusicdl = ref(false);
        const musicPreset = ref('default');
        const musicSearchType = ref('song');
        const musicIncludeLocal = ref(false);
        const musicFilenameTemplate = ref('{artist}/{name} - {artist}');
        const musicEmbedMeta = ref(false);
        // 整批点下载时默认不再下第二份已有同名成品的歌；单首点「下载」不受这个约束
        const musicSkipExisting = ref(true);
        // 正在换源的行 id：行内按钮各自转圈，批量按钮整轮置灰
        const musicSwitching = ref([]);
        const musicHideUnavailable = ref(true);
        // Qobuz / Tidal 官方曲库的元数据参照行：默认关，勾上才每次多问一次
        const musicIncludeReference = ref(false);
        // 搬运版守门：和后端 music_block_reupload 一样默认关，Spotify/Apple 的音频本来就要转链取
        const musicBlockReupload = ref(false);
        // 音质要求：档位阶梯写死在 musicdl 每个源里，钉不住，所以这一项只做「多候选挑达标的」
        // 与「下完核对成品实际档位」，勾了不达标不下才整首跳过。选项表由后端回，界面不抄第二份
        const musicQualitySpec = ref({ format: '', min_bit_depth: 0, min_sample_rate: 0, min_bitrate: 0, strict: false });
        const musicQualityOptions = ref({
          format: [{ value: '', label: '不限' }],
          bit_depth: [{ value: 0, label: '位深不限' }],
          sample_rate: [{ value: 0, label: '采样率不限' }],
          bitrate: [{ value: 0, label: '码率不限' }],
        });
        // 与后端 quality_spec_label 同一写法，界面上这句话要能对上日志里那句「本次音质要求」
        function qualitySpecLabel(s) {
          s = s || {};
          const parts = [];
          if (s.format === 'lossless') parts.push('无损');
          else if (s.format) parts.push(String(s.format).toUpperCase());
          if (s.min_bit_depth) parts.push(s.min_bit_depth + 'bit 以上');
          if (s.min_sample_rate) parts.push((s.min_sample_rate / 1000).toFixed(1).replace(/\.0$/, '') + 'kHz 以上');
          if (s.min_bitrate) parts.push(s.min_bitrate + 'k 以上');
          return parts.join('、');
        }
        const musicQualitySummary = computed(() => qualitySpecLabel(musicQualitySpec.value));
        // 底部常驻播放条：整份界面只有一个 <audio>，切页不销毁，所以歌不会被切段
        const player = reactive({ url: '', title: '', sub: '', cover: '', queue: [], idx: -1, from: '' });
        const playerEl = ref(null);
        const playerPlaying = ref(false);
        const playerTime = ref(0);
        const playerDur = ref(0);
        const playerVol = ref(0.8);
        const playerMuted = ref(false);
        // 拖动进度条时先按手上的值显示，否则 timeupdate 会把滑块拽回播放位置
        const playerSeeking = ref(false);
        const playerSeekVal = ref(0);
        const musicLrcLines = ref([]);
        const musicLrcActive = ref(-1);
        const musicStrategy = ref({
          mode: 'parallel',
          order: 'as_is',
          search_size: 12,
          max_retries: 3,
          connect_timeout: 10,
          read_timeout: 30,
          threads_per_source: 5,
          per_source_budget: 300,
          dedupe: 'global',
          match_sources: ['NeteaseMusicClient', 'QQMusicClient', 'MiguMusicClient',
                          'KugouMusicClient', 'KuwoMusicClient'],
        });
        // 每次搜索后「某源 0 条」的人话原因，[源, 原因] 列表
        const musicSourceErrors = ref([]);
        const musicSources = ref(['MiguMusicClient','NeteaseMusicClient','QQMusicClient','AppleMusicClient','SpotifyMusicClient']);
        const musicSourceOptions = ref(['MiguMusicClient','NeteaseMusicClient','QQMusicClient','KuwoMusicClient','QianqianMusicClient','KugouMusicClient','BilibiliMusicClient','YouTubeMusicClient','SoundCloudMusicClient','SpotifyMusicClient','AppleMusicClient','XimalayaMusicClient']);
        // 「匹配源」的候选与「搜索源」一致，都能选。Spotify/Apple 的取址要经第三方转链
        // （musicdl 打 spotubedl 一类接口），能下但每首约十秒、时常失败，所以标出来、不进默认。
        const musicMatchSourceOptions = computed(() => (musicSourceOptions.value || []).map((s) => ({
          value: s,
          label: s.replace('MusicClient', '') + (/^(Spotify|Apple)/.test(s) ? '（取址慢）' : ''),
        })));
        const musicPresetOptions = [
          { value: 'default', label: '默认组合' },
          { value: 'cn', label: '国内扩展' },
          { value: 'global', label: '国际流媒体' },
          { value: 'radio', label: '有声 / 电台' },
          { value: 'all_common', label: '常用混合' },
          { value: 'custom', label: '自定义' },
        ];
        const MUSIC_PRESET_FALLBACK = {
          default: ['MiguMusicClient','NeteaseMusicClient','QQMusicClient','AppleMusicClient','SpotifyMusicClient'],
          cn: ['MiguMusicClient','NeteaseMusicClient','QQMusicClient','KuwoMusicClient','QianqianMusicClient','KugouMusicClient','BilibiliMusicClient'],
          global: ['YouTubeMusicClient','SoundCloudMusicClient','SpotifyMusicClient','AppleMusicClient'],
          radio: ['XimalayaMusicClient','LizhiMusicClient','QingtingMusicClient'],
          all_common: ['MiguMusicClient','NeteaseMusicClient','QQMusicClient','KuwoMusicClient','KugouMusicClient','YouTubeMusicClient','SoundCloudMusicClient'],
        };
        const MUSIC_CN_HINTS_FALLBACK = ['Migu','Netease','QQ','Kuwo','Qianqian','Kugou','Bilibili','Ximalaya','FiveSing','Bodian'];
        const MUSIC_GLOBAL_HINTS_FALLBACK = ['YouTube','SoundCloud','Spotify','Apple','Deezer','TIDAL','Qobuz','Jamendo'];
        function musicPresetMap() {
          return window.__musicPresets || MUSIC_PRESET_FALLBACK;
        }
        function sameSourceSet(a, b) {
          return a.length === b.length && [...a].sort().join('|') === [...b].sort().join('|');
        }
        // 下拉只反映真实勾选，不再写死成「默认」
        function syncMusicPreset() {
          const presets = musicPresetMap();
          const hit = Object.keys(presets).find(k => sameSourceSet(presets[k] || [], musicSources.value));
          musicPreset.value = hit || 'custom';
        }
        // 跟 music_search._order_sources 同一套规则，界面上才能看见排序生效
        function orderMusicSources(list, order) {
          if (order === 'as_is' || !list.length) return list.slice();
          const cnHints = (window.__musicSourceHints || {}).cn || MUSIC_CN_HINTS_FALLBACK;
          const glHints = (window.__musicSourceHints || {}).global || MUSIC_GLOBAL_HINTS_FALLBACK;
          const isCn = s => cnHints.some(h => s.includes(h));
          const isGl = s => glHints.some(h => s.includes(h));
          const cn = list.filter(isCn);
          const gl = list.filter(s => isGl(s) && !isCn(s));
          const other = list.filter(s => !cn.includes(s) && !gl.includes(s));
          return order === 'cn_first' ? [...cn, ...other, ...gl] : [...gl, ...other, ...cn];
        }
        const musicSourceOrdered = computed(() => {
          const sel = orderMusicSources(musicSources.value, musicStrategy.value.order);
          return [...sel, ...musicSourceOptions.value.filter(s => !musicSources.value.includes(s))];
        });
        watch(musicSources, syncMusicPreset, { deep: true });
        const musicPlaylistUrl = ref('');
        const musicPlaylistMode = ref('fast');
        const musicCookies = ref('');
        const musicSelected = ref([]);
        const searchPlatform = ref('all');
        const searchContentType = ref('all');
        const searchSort = ref('relevance');
        const searchTotal = ref(0);
        const searchTruncated = ref(false);
        const searchNotes = ref([]);   // 后端按平台给出的「这一路为什么没结果」（风控 / 要登录 / 真的没有）
        const searchResults = ref([]);
        const searching = ref(false);
        const platformCookies = ref([]);
        const cookieIssueCount = computed(() => platformCookies.value.filter(p => p.login_issue).length);
        const syncFileInput = ref(null);
        const liveTasks = computed(() => tasks.value.filter(t => t.is_live || (t.title || '').includes('直播')));
        const liveTasksActive = computed(() => liveTasks.value.filter(t => isLiveRunning(t)));
        function isLiveRunning(t) {
          return t && ['downloading', 'queued', 'paused'].includes(t.status);
        }
        function liveAutoSaveText(t) {
          const lim = Number((t && t.live_limit_min) || 0);
          if (!lim || !isLiveRunning(t)) return '';
          const left = lim * 60 - Number(t.elapsed_sec || 0);
          return left > 0 ? `还剩 ${Math.max(1, Math.ceil(left / 60))} 分钟自动保存` : '正在自动保存…';
        }
        function fileBasename(p) {
          if (!p) return '';
          const s = String(p).replace(/\\/g, '/');
          return s.split('/').pop() || s;
        }
        async function openLiveFile(t) {
          try {
            await api('/api/open-folder', { method: 'POST', body: JSON.stringify({ path: t.filepath || '' }) });
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '打开失败');
          }
        }
        async function clearFinishedLiveTasks() {
          const ids = liveTasks.value.filter(t => !isLiveRunning(t)).map(t => t.id);
          if (!ids.length) {
            ElementPlus.ElMessage.info('暂无已结束的任务');
            return;
          }
          await api('/api/delete', { method: 'POST', body: JSON.stringify({ ids }) });
          await loadTasks();
          ElementPlus.ElMessage.success('已清理 ' + ids.length + ' 条');
        }
        const fileSearch = ref('');
        const fileSort = ref('name');
        const urlFileInput = ref(null);
        const musicNeedsMatch = computed(() => musicResults.value.filter(r => r && r.needs_match).length);
        const musicScoreLine = computed(() => {
          const hit = musicResults.value.find(r => r && r.match_accept);
          return hit ? hit.match_accept : 85;
        });
        const musicHasScore = computed(() => musicResults.value.some(r => r && r.score !== null && r.score !== undefined));

        /* ---- 表头排序：各表共用。点同一列切升/降序，换列回到该列默认方向 ---- */
        const FILE_DIR = { name: 'asc', size: 'desc', mtime: 'desc' };
        const fileSortDir = ref('asc');
        function toggleSort(state, key, dirs) {
          if (state.key === key) state.dir = state.dir === 'asc' ? 'desc' : 'asc';
          else { state.key = key; state.dir = (dirs && dirs[key]) || 'asc'; }
          if (state.t) logSort(state.t, state.key, state.dir);
        }
        /* 列名 → 中文，排序留痕用；未收录的列名原样写出 */
        const COL_LABELS = {
          name: '文件名', title: '标题', uploader: '上传方', platform: '平台', kind: '类型',
          res: '分辨率', duration: '时长', size: '大小', mtime: '修改时间', time: '时间',
          status: '状态', id: 'ID', ext: '封装', tbr: '码率', url: '链接',
          last_check: '上次检查', new_count: '新增', date: '日期', views: '播放量',
          artists: '歌手', album: '专辑',
        };
        function logSort(listTitle, key, dir) {
          logAction(`「${listTitle}」按${COL_LABELS[key] || key}${dir === 'asc' ? '升序' : '降序'}排序`);
        }
        function sortIcon(state, key) {
          if (state.key !== key) return '↕';
          return state.dir === 'asc' ? '↑' : '↓';
        }
        function sortKey(v) {
          return String(v == null ? '' : v).replace(/^[^\p{L}\p{N}]+/u, '');
        }
        function applySort(list, state, getters) {
          const g = getters[state.key];
          if (!g) return list;
          const dir = state.dir === 'asc' ? 1 : -1;
          return list.slice().sort((a, b) => {
            const va = g(a); const vb = g(b);
            if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * dir;
            return sortKey(va).localeCompare(sortKey(vb), 'zh') * dir;
          });
        }
        /* el-table 的 @sort-change 转成与原生表 toggleSort 同一套语义：同列切升降、换列回默认方向 */
        function nextSort(state, prop, order, dirs) {
          if (state.key !== prop) return { key: prop, dir: (dirs && dirs[prop]) || 'asc' };
          return { key: prop, dir: state.dir === 'asc' ? 'desc' : 'asc' };
        }
        /* 长列表分页：每页 LIST_PAGE_SIZE 条，排序/筛选后的完整列表进来，当前页的切片出去 */
        const LIST_PAGE_SIZE = 50;
        function usePager(source) {
          const page = ref(1);
          const total = computed(() => source().length);
          const show = computed(() => total.value > LIST_PAGE_SIZE);
          const paged = computed(() => {
            const start = (page.value - 1) * LIST_PAGE_SIZE;
            return source().slice(start, start + LIST_PAGE_SIZE);
          });
          watch(total, (n) => {
            const last = Math.max(1, Math.ceil(n / LIST_PAGE_SIZE));
            if (page.value > last) page.value = last;
          });
          return reactive({ page, total, show, paged, pageSize: LIST_PAGE_SIZE });
        }
        function onFileSortChange({ prop, order }) {
          if (!order) return;
          const key = prop === 'size' ? 'size' : prop === 'mtime' ? 'mtime' : 'name';
          fileSort.value = key;
          fileSortDir.value = order === 'ascending' ? 'asc' : 'desc';
          logSort('文件列表', key, fileSortDir.value);
        }
        function cmp(key) {
          return (a, b) => {
            const va = a == null ? null : a[key];
            const vb = b == null ? null : b[key];
            if (typeof va === 'number' && typeof vb === 'number') return va - vb;
            return sortKey(va).localeCompare(sortKey(vb), 'zh');
          };
        }
        const HIST_DIR = { time: 'desc', title: 'asc', status: 'asc' };
        const histSort = ref({ key: 'time', dir: 'desc', t: '下载历史' });
        const HIST_GETTERS = { time: x => x.time || '', title: x => x.title || '', status: x => x.status || '' };
        const historySorted = computed(() => applySort(history.value, histSort.value, HIST_GETTERS));

        const FMT_DIR = { id: 'asc', res: 'desc', ext: 'asc', tbr: 'desc', size: 'desc' };
        const fmtSort = ref({ key: '', dir: 'asc', t: '可用格式' });
        const FMT_GETTERS = {
          id: f => f.format_id || '',
          res: f => f.height || 0,
          ext: f => f.ext || '',
          tbr: f => Number(f.tbr) || 0,
          size: f => f.filesize || f.filesize_est || 0
        };
        const formatsSorted = computed(() => applySort((mediaInfo.value && mediaInfo.value.formats) || [], fmtSort.value, FMT_GETTERS));

        const SUB_DIR = { kind: 'asc', title: 'asc', status: 'asc', url: 'asc', last_check: 'desc', new_count: 'desc' };
        const subSort = ref({ key: '', dir: 'asc', t: '订阅列表' });
        const SUB_GETTERS = {
          kind: s => s.kind || '',
          title: s => s.title || '',
          status: s => subStatus(s).text || '',
          url: s => s.url || '',
          last_check: s => s.last_check || '',
          new_count: s => s.new_count || 0
        };
        const subsSorted = computed(() => applySort(subs.value, subSort.value, SUB_GETTERS));

        const filteredFiles = computed(() => {
          let list = fileItems.value.slice();
          const q = (fileSearch.value || '').trim().toLowerCase();
          if (q) list = list.filter(f => (f.name || '').toLowerCase().includes(q));
          const s = fileSort.value;
          const dir = fileSortDir.value === 'asc' ? 1 : -1;
          list.sort((a, b) => {
            if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1;
            if (s === 'size') return ((a.size || 0) - (b.size || 0)) * dir;
            if (s === 'mtime') return String(a.mtime || '').localeCompare(String(b.mtime || '')) * dir;
            return sortKey(a.name).localeCompare(sortKey(b.name), 'zh') * dir;
          });
          return list;
        });
        /* 文件行「更多」下拉：command 形如「方法名|行号」，行号取当前页切片内的下标。
           列排序全部走 sortable="custom"，Element 不再二次排序，故 $index 与当页切片一一对应。 */
        const FILE_ACTIONS = {
          aiTranscribe, aiTranslateSrt, aiPipeline, showPipeline, aiDemucs, analyzeAudioFile,
          aiTts, aiCalibrateSrt, exportBilingual, openBurn, openPicard, mbTagFile,
          mbEnrichFile, fingerprintFile, guessTagsFile,
        };
        function runFileAction(command) {
          const raw = String(command == null ? '' : command);
          const sep = raw.lastIndexOf('|');
          if (sep < 0) return;
          const fn = FILE_ACTIONS[raw.slice(0, sep)];
          /* 表格里的 $index 是当前页内下标，必须按当页切片取行，不能用全量列表 */
          const row = pagers.files.paged[Number(raw.slice(sep + 1))];
          if (typeof fn !== 'function' || !row) return;
          fn(row);
        }
        /* 结果卡在文件表上方，而表格常有 50 行：不滚过去，点了就像没反应 */
        function revealCard(id) {
          nextTick(() => {
            const el = document.getElementById(id);
            if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
          });
        }
        const browserOptions = [
          { label: 'Chrome', value: 'chrome' },
          { label: 'Edge', value: 'edge' },
          { label: 'Firefox', value: 'firefox' },
          { label: 'Brave', value: 'brave' },
          { label: 'Opera', value: 'opera' },
          { label: 'Chromium', value: 'chromium' },
        ];
        const submitting = ref(false);
        const updatingYtdlp = ref(false);
        const updatingWhisper = ref(false);
        const updatingFfmpeg = ref(false);
        const updatingNm3u8 = ref(false);
        const components = ref([]);
        const compInfo = ref({});
        const updatingComp = ref('');
        const latestBusy = ref(false);
        const pathBusy = ref(false);

        let pollTimer = null;

        function friendlyError(raw) {
          const s = String(raw || '');
          // 后端已经点名「原因：…；该做什么」，或带上了命中的判定标记（依据 …）：原样上屏。
          // 改写会把站点返回码、原话和命中的标记弄丢，只剩下界面模板那句套话。
          if (s.includes('原因：') || s.includes('（依据 ')) return s;
          const tail = s.length > 120 ? s.slice(0, 120) + '…' : s;
          const withTail = (msg) => (/^[\[(']/.test(s) ? msg + '（原始：' + tail + '）' : msg);
          // 分类说法不能替掉站点原文：下面几条一律把原话附在后面
          const keepTail = (msg) => (msg + (s && !msg.includes(s.slice(0, 24)) ? '（原始：' + tail + '）' : ''));
          if (/10054|ConnectionResetError|Connection aborted|connection was reset|ECONNRESET/i.test(s))
            return withTail('连接被远端强制中断：通常为网络被重置、站点屏蔽或需要代理。可在「设置 → 网络与并发」填写代理地址，或将镜像前缀留空/更换后重试');
          if (/timed?\s*out|TimeoutError|read timeout/i.test(s))
            return withTail('请求超时：远端无响应或网速过慢，请稍后重试；必要时使用代理');
          if (/getaddrinfo failed|NameResolution|Name or service not known|nodename nor servname|ERR_NAME_NOT_RESOLVED/i.test(s))
            return withTail('域名解析失败：请检查本机网络或 DNS，境外站点需要在设置中配置代理');
          if (/status_code['"= ]{0,3}2483|请先登录|fresh cookies?.*(needed|are needed)/i.test(s))
            return keepTail('站点要求先登录才回答（见到返回码 2483、「请先登录」或 yt-dlp 的「Fresh cookies are needed」）：'
                            + '请在「设置 → 多平台 Cookie」里的「抖音/TikTok」导入已登录浏览器的 Cookie，或改用「粘贴分享链接 → 直接下载」');
          if (/__ac_nonce|byted_acrawler|_\$jsvmprt|__ac_signature/i.test(s))
            return keepTail('站点把这个请求当成脚本访问了，回的是需要执行 JS 的校验页（见到 '
                            + (s.match(/__ac_nonce|byted_acrawler|_\$jsvmprt|__ac_signature/i)[0])
                            + '）：这条路径拿不到内容，请在「设置 → 多平台 Cookie」里的「抖音/TikTok」导入已登录浏览器的 Cookie');
          if (/sign in to confirm (you'?re not a bot|your age)|not a bot|captcha/i.test(s))
            return withTail('站点判定为机器人访问：在「设置 → Cookie」从已登录的浏览器导入 Cookie，或开启「HTTP TLS 指纹模拟」并降低并发后重试');
          if (/age[_ ]restricted|confirm your age|年龄限制/i.test(s))
            return withTail('年龄限制内容：需登录具备权限的账号 Cookie（在设置 → Cookie 中导入）');
          if (/members.only|this video is private|private video|仅会员|会员专属/i.test(s))
            return withTail('私有或会员专属内容：需使用有权限的账号 Cookie 才能下载');
          if (/login required|log in|account required|授权|需要登录/i.test(s))
            return withTail('该站点要求登录：在「设置 → Cookie」导入已登录浏览器的 Cookie 后重试');
          if (/\bdrm\b|widevine|内容.*加密.*无法解密/i.test(s))
            return withTail('内容为 DRM 加密，本工具无法解密，不支持此类下载');
          if (/available in your country|not available in your (country|region)|blocked in your|地区限制|按地区/i.test(s))
            return withTail('该内容按地区/版权限制：需更换出口网络（在设置 → 网络与并发填写代理），或导入对应地区的 Cookie');
          if (/http error 401|Unauthorized/i.test(s))
            return withTail('身份验证失败（401）：Cookie 可能已过期，请重新导入');
          if (/http error 403|forbidden|access denied/i.test(s))
            return withTail('站点拒绝访问（403）：通常需要登录 Cookie 或代理，也可能是链接已过期，请重新复制链接');
          if (/http error 404|video unavailable|no video available|unable to find a video|视频不存在|已删除/i.test(s))
            return withTail('视频不存在、已删除或地址有误：请确认链接可在浏览器中正常打开');
          if (/\b429\b|too many requests|rate ?limit/i.test(s))
            return withTail('命中站点限流（429）：自动退避后仍未成功。请在「设置 → 网络与并发」调低并发数和每站点并发，或稍后重试');
          if (/no video formats|no formats|requested format is not available|unavailable formats/i.test(s))
            return withTail('没有可下载的画质：可能仅提供会员专享格式。请改用「最佳」或降低分辨率后重试，避免使用「指定格式」');
          if (/unsupported url|no extractor|extractor not found/i.test(s))
            return withTail('该网址暂无法解析：可安装或更新 yt-dlp（设置 → 组件与依赖），或用浏览器扩展嗅探真实媒体地址');
          if (/ffmpeg|ffprobe/i.test(s) && /not (found|installed)|is not recognized|no such file|未安装|缺失/i.test(s))
            return withTail('缺少 FFmpeg：请在「设置 → 组件与依赖」点击 FFmpeg 的更新/安装按钮');
          if (/直播.*(未开始|已结束)|livestream.*(not started|ended)|is not live/i.test(s))
            return withTail('直播未开始或已结束：请开播后再点击录制');
          if (/SSL|TLS|certificate verify failed|CERTIFICATE_VERIFY/i.test(s))
            return withTail('HTTPS 证书校验失败：可在「设置 → 网络与并发」开启「跳过 SSL 证书校验」，或关闭「HTTP TLS 指纹模拟」再试');
          if (/Proxy|SOCKS|Cannot connect to proxy/i.test(s))
            return withTail('代理不可用：请检查设置中的代理地址与端口是否在运行');
          if (/No module named/i.test(s))
            return withTail('缺少依赖：请在「设置 → 组件与依赖」点击对应项的安装按钮补齐');
          return s || '请求失败';
        }

        /* ---- 操作留痕：用户在界面上点了什么，日志页要能看到一条人话记录 ---- */
        const UI_EVENT_PATH = '/api/ui_event';
        const SENSITIVE_RE = /token|secret|password|cookie|api_hash|sendkey/i;
        function logAction(text, level) {
          try {
            const t = String(text || '').replace(/[\r\n]+/g, ' ').trim();
            if (!t) return;
            fetch(UI_EVENT_PATH, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                text: SENSITIVE_RE.test(t) ? '[已隐藏敏感参数]' : t,
                level: level === 'warning' ? 'warning' : 'info',
              }),
            }).catch(() => {});
          } catch (_) {}
        }
        const ACTION_NAMES = {
          '/api/download': '加入下载队列',
          '/api/analyze': '解析网址',
          '/api/search': '聚合搜索',
          '/api/pause': '暂停任务',
          '/api/resume': '继续任务',
          '/api/stop': '停止下载',
          '/api/retry': '重试全部失败任务',
          '/api/retry-one': '重试任务',
          '/api/delete': '清理已结束任务',
          '/api/clear-finished': '清除已完成任务',
          '/api/cleanup-parts': '清理未完成的分片文件',
          '/api/tasks/delete': '删除任务',
          '/api/tasks/edit': '修改任务设置',
          '/api/tasks/pin': '置顶任务',
          '/api/tasks/unpin': '取消置顶任务',
          '/api/tasks/top': '把任务移到队首',
          '/api/tasks/later': '把任务设为稍后下载',
          '/api/tasks/start-later': '启动稍后下载的任务',
          '/api/config': '保存设置',
          '/api/auth/login': '登录访问保护',
          '/api/auth/logout': '退出登录',
          '/api/auth/password': '设置访问口令',
          '/api/auth/machine_token': '重置机器令牌',
          '/api/auth/unlock': '解锁登录锁定',
          '/api/components/update-all': '一键更新组件与依赖',
          '/api/components/update-check': '检测组件上游版本',
          '/api/open-folder': '打开下载目录',
          '/api/browse': '选择本机文件或文件夹',
          '/api/test-cookie': '检测浏览器登录凭证可用性',
          '/api/platforms/cookies': '读取浏览器登录凭证',
          '/api/platforms/cookies/save-text': '粘贴保存登录凭证',
          '/api/platforms/cookies/clear-flag': '清除平台 Cookie 的登录态标记',
          '/api/files/delete': '删除文件',
          '/api/files/clear-archive': '清空已下载记录',
          '/api/files/zip': '打包下载文件',
          '/api/diagnostics/export': '导出诊断包',
          '/api/history/clear': '清空下载历史',
          '/api/logs/clear': '清空运行日志',
          '/api/library/scan': '扫描资源库',
          '/api/transcode': '转码文件',
          '/api/subtitle/glossary_check': '检查字幕术语表',
          '/api/config/speed_windows/check': '检查限速时段格式',
          '/api/config/run_window/check': '检查队列定时窗格式',
          '/api/subtitle/qc': '检查字幕翻译质量',
          '/api/subtitle/rewrap': '重排字幕每行字数',
          '/api/sniff': '嗅探网页媒体',
          '/api/sniff/browser/start': '启动浏览器嗅探',
          '/api/sniff/browser/stop': '停止浏览器嗅探',
          '/api/sniff/browser/clear': '清空嗅探结果',
          '/api/sniff/download': '下载嗅探到的地址',
          '/api/sniff/download_merge': '下载并合并嗅探到的分片',
          '/api/catcatch/import-config': '导入猫抓配置文件的正则规则',
          '/api/catcatch/rules/toggle': '启用或停用猫抓规则',
          '/api/catcatch/rules/delete': '删除猫抓规则',
          '/api/catcatch/rules/clear': '清空猫抓规则',
          '/api/live/end': '结束直播录制',
          '/api/live/monitors/add': '添加直播监控',
          '/api/live/monitors/remove': '移除直播监控',
          '/api/live/monitors/pause': '暂停直播监控',
          '/api/live/monitors/resume': '恢复直播监控',
          '/api/live/monitors/scan': '扫描直播监控',
          '/api/live/monitors/set': '修改直播房间录制设置',
          '/api/subs/add': '添加订阅',
          '/api/subs/remove': '删除订阅',
          '/api/subs/toggle': '启用或停用订阅',
          '/api/subs/rules': '保存订阅规则',
          '/api/subs/scan': '扫描全部订阅',
          '/api/subs/scan-one': '扫描单个订阅',
          '/api/subs/backfill': '按日期回填订阅历史',
          '/api/subs/preview': '预览订阅同步计划',
          '/api/subs/archived/clear': '清空上游删除归档',
          '/api/subs/archived': '查看上游删除归档',
          '/api/favorites/download': '批量下载收藏内容',
          '/api/music/search': '搜索音乐',
          '/api/music/download': '下载音乐',
          '/api/music/playlist': '解析音乐歌单',
          '/api/music/probe': '探测音乐来源',
          '/api/music/check_quality': '核对成品音质',
          '/api/music/lyrics': '获取歌词',
          '/api/music/local_scan': '扫描本地音乐库',
          '/api/music/install': '安装音乐下载组件',
          '/api/music/tag': '写入音乐标签',
          '/api/music/guess_tags': '自动推测音乐标签',
          '/api/music/fingerprint': '音频指纹识别',
          '/api/music/mb_lookup': '查询 MusicBrainz 匹配',
          '/api/music/mb_enrich': '用 MusicBrainz 补全标签',
          '/api/ai/batch': '批量 AI 处理',
          '/api/ai/pipeline': '运行 AI 流水线',
          '/api/ai/analyze': '音频分析',
          '/api/ai/transcribe': '语音转写',
          '/api/ai/realtime': '准实时转写翻译',
          '/api/ai/translate_srt': '翻译字幕',
          '/api/ai/srt_calibrate': '校正字幕',
          '/api/ai/srt/save': '保存逐句字幕校对',
          '/api/ai/subtitle_export': '导出字幕',
          '/api/ai/hardsub': '烧录硬字幕',
          '/api/ai/hardsub_stop': '停止硬字幕烧录',
          '/api/ai/demucs': '人声分离',
          '/api/ai/tts': '字幕配音',
          '/api/ai/install_voice': '安装语音模型包',
          '/api/telegram/test': '测试 Telegram 通知',
          '/api/telegram/list': '拉取 Telegram 频道内容',
          '/api/telegram/mt/config': '保存 Telegram 会话凭据',
          '/api/telegram/mt/send-code': '发送 Telegram 登录验证码',
          '/api/telegram/mt/sign-in': '提交 Telegram 登录验证码',
          '/api/telegram/mt/logout': '退出 Telegram 登录',
          '/api/telegram/mt/list': '拉取 Telegram 会话内容',
          '/api/telegram/mt/ack': '标记 Telegram 频道已读',
          '/api/wecom/test': '测试企业微信通知',
          '/api/storage/test': '测试云存储连通',
          '/api/bili/qr/poll': '轮询 B 站扫码登录结果',
          '/api/music/cookies': '保存音乐平台登录 Cookie',
          '/api/music/netease/qr/generate': '获取网易云登录二维码',
          '/api/music/netease/qr/poll': '轮询网易云扫码登录结果',
          '/api/risk/preset': '应用反风控预设',
          '/api/po_token/check': 'PO 凭证可用性自检',
          '/api/net/use_system_proxy': '改用系统代理',
          '/api/net/reset': '重置网络设置',
          '/api/queue/throttle_reset': '解除站点降速',
          '/api/env/path': '更新 PATH 环境变量',
          '/api/plugins/reload': '重载解析插件',
          '/api/torrent/upload': '上传种子文件',
          '/api/torrent/select': '改选种子内文件',
          '/api/torrent/stop-seed': '停止做种',
          '/api/sync/import': '导入配置备份',
          '/api/update/whisper': '更新 Whisper 模型',
          '/api/update/n_m3u8dl': '更新 N_m3u8DL-RE',
          '/api/update/ytdlp': '更新 yt-dlp',
          '/api/update/ffmpeg': '更新 FFmpeg',
          '/api/update/pkg': '更新 Python 依赖',
        };
        const ACTION_KEYS = Object.keys(ACTION_NAMES).sort((a, b) => b.length - a.length);
        function actionName(path) {
          const clean = String(path || '').split('?')[0];
          if (ACTION_NAMES[clean]) return ACTION_NAMES[clean];
          const hit = ACTION_KEYS.find((k) => clean.indexOf(k) === 0);
          return hit ? ACTION_NAMES[hit] : '调用 ' + clean.replace(/^\/api\//, '');
        }

        /* 访问保护（登录）：开关、口令、锁定名单都在「设置 → 访问保护」这一张卡里。
           这里只负责两件事：非本机来的连接被 401 挡下时弹登录窗，以及那张卡要的读数。 */
        const auth = ref({ enabled: false, enforcing: false, password_set: false, loopback: true,
                           client_ip: '', authorized: true, locked: false, lock_left: 0, locks: [],
                           machine_token: '', note: '', session_hours: 12, remember_days: 30,
                           max_fails: 5, lock_minutes: 15 });
        const authGate = reactive({ needed: false, reason: '', pwd: '', remember: false, busy: false, error: '' });
        const authForm = reactive({ current: '', password: '' });
        const authBusy = ref(false);
        const authTokenShown = ref(false);

        async function loadAuthStatus(quiet) {
          try {
            const r = await api('/api/auth/status', { noLog: true });
            if (!r) return;
            auth.value = r;
            authGate.needed = !!(r.enabled && r.enforcing && !r.authorized);
            if (!authGate.needed) authGate.error = '';
            authForm.current = '';
            authForm.password = '';
          } catch (e) {
            if (!quiet) ElementPlus.ElMessage.error('读不到登录保护状态：' + String(e.message || e));
          }
        }

        async function doLogin() {
          const pw = String(authGate.pwd || '');
          if (!pw) { authGate.error = '先把口令填上'; return; }
          authGate.busy = true;
          authGate.error = '';
          try {
            await api('/api/auth/login', {
              method: 'POST', noLog: true,
              body: JSON.stringify({ password: pw, remember: !!authGate.remember }),
            });
            authGate.needed = false;
            authGate.pwd = '';
            // 之前所有数据接口都被门挡住了，界面是空的：整页重拉一次比逐个补调用可靠
            ElementPlus.ElMessage.success('已登录，正在载入界面…');
            setTimeout(() => location.reload(), 400);
          } catch (e) {
            // 423（还在锁定期）与 401（还能试几次）后端都写清了，原样上屏
            authGate.error = String(e.message || e);
          } finally {
            authGate.busy = false;
          }
        }

        async function saveAuthKnobs() {
          authBusy.value = true;
          try {
            await api('/api/config', {
              method: 'POST', uiName: '保存访问保护设置',
              body: JSON.stringify({
                web_auth_enabled: !!settings.value.web_auth_enabled,
                web_auth_session_hours: Number(settings.value.web_auth_session_hours) || 12,
                web_auth_remember_days: Number(settings.value.web_auth_remember_days) || 30,
                web_auth_max_fails: Number(settings.value.web_auth_max_fails) || 5,
                web_auth_lock_minutes: Number(settings.value.web_auth_lock_minutes) || 15,
              }),
            });
            await loadAuthStatus(true);
            ElementPlus.ElMessage.success('访问保护设置已保存');
          } catch (e) {
            // 还没设口令就开开关会被后端顶回来：开关拨回原样，别让界面显示一个没生效的状态
            settings.value.web_auth_enabled = !settings.value.web_auth_enabled;
            ElementPlus.ElMessage.error(String(e.message || e));
          } finally {
            authBusy.value = false;
          }
        }

        async function applyAuthPassword() {
          const pw = String(authForm.password || '');
          if (pw.length < 6) {
            ElementPlus.ElMessage.warning('口令至少 6 个字符');
            return;
          }
          authBusy.value = true;
          try {
            await api('/api/auth/password', {
              method: 'POST', uiName: '设置访问口令',
              body: JSON.stringify({ password: pw, current: authForm.current || '' }),
            });
            authForm.current = '';
            authForm.password = '';
            await loadAuthStatus(true);
            ElementPlus.ElMessage.success('口令已写好（只存加盐哈希，读不回来）。非本机的旧登录状态要重登一次。');
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          } finally {
            authBusy.value = false;
          }
        }

        async function copyMachineToken() {
          const tok = String((auth.value || {}).machine_token || '');
          if (!tok) {
            ElementPlus.ElMessage.warning('这串读不到：本机以外的浏览器不返回令牌，用 127.0.0.1 打开再复制');
            return;
          }
          try {
            await navigator.clipboard.writeText(tok);
            ElementPlus.ElMessage.success('令牌已复制（这是能开门的东西，别贴群里）');
          } catch (e) {
            authTokenShown.value = true;
            ElementPlus.ElMessage.warning('这个浏览器不给剪贴板权限（非 HTTPS 常见）：已经显示出来了，手抄一份');
          }
        }

        function rotateMachineToken() {
          ElementPlus.ElMessageBox.confirm('重置后旧令牌立刻失效，用它的脚本要换成新的。',
            '重置机器令牌', { type: 'warning', confirmButtonText: '重置', cancelButtonText: '先不' })
            .then(() => api('/api/auth/machine_token', { method: 'POST', uiName: '重置机器令牌' }))
            .then(r => {
              auth.value.machine_token = (r && r.machine_token) || '';
              authTokenShown.value = true;
              ElementPlus.ElMessage.success('新令牌已生成');
            })
            .catch(e => { if (e && e.message) ElementPlus.ElMessage.error(String(e.message || e)); });
        }

        function unlockIp(ip) {
          api('/api/auth/unlock', { method: 'POST', uiName: '解锁登录锁定', body: JSON.stringify({ ip }) })
            .then(r => { auth.value.locks = (r && r.locks) || []; ElementPlus.ElMessage.success('已解锁 ' + ip); })
            .catch(e => ElementPlus.ElMessage.error(String(e.message || e)));
        }

        function unlockAll() {
          ElementPlus.ElMessageBox.confirm('清掉全部锁定与失败计数：正在被锁的来源马上又能接着试口令。',
            '全部解锁', { type: 'warning', confirmButtonText: '全部解锁', cancelButtonText: '先不清' })
            .then(() => api('/api/auth/unlock', { method: 'POST', uiName: '清空登录锁定', body: JSON.stringify({}) }))
            .then(r => { auth.value.locks = (r && r.locks) || []; ElementPlus.ElMessage.success('已清空'); })
            .catch(e => { if (e && e.message) ElementPlus.ElMessage.error(String(e.message || e)); });
        }

        async function api(path, options = {}) {
          const uiName = options.uiName;      // 同一个接口被不同按钮共用时，日志要写清是哪一下
          const noLog = options.noLog === true;   // 定时轮询的写操作别刷日志，登录那一下后端会记
          const init = { ...options };
          delete init.uiName;
          delete init.noLog;
          // 埋点只针对写操作：GET 多是轮询，记了会把日志刷爆；/api/ui_event 自身必须排除，否则无限递归
          const tracked = String(init.method || 'GET').toUpperCase() !== 'GET'
            && String(path).indexOf(UI_EVENT_PATH) !== 0 && !noLog;
          const res = await fetch(path, {
            headers: { 'Content-Type': 'application/json' },
            ...init,
          });
          if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            if (res.status === 401 && err && err.auth_required) {
              // 被登录门挡下（含会话过期）：弹登录窗就行，别把同一句 401 刷成一片红点
              authGate.needed = true;
              authGate.reason = String(err.reason || 'empty');
            }
            if (tracked) logAction((uiName || actionName(path)) + '（失败）', 'warning');
            throw new Error(friendlyError(err.detail || res.statusText));
          }
          if (tracked) logAction(uiName || actionName(path));
          return res.json();
        }

        async function loadStatus() {
          try {
            status.value = await api('/api/status');
          } catch (e) {
            ElementPlus.ElMessage.error('环境检测失败: ' + e.message);
          }
        }

        async function checkEnv() {
          await loadStatus();
          ElementPlus.ElMessageBox.alert(
            `FFmpeg：${status.value.ffmpeg}\n路径：${status.value.ffmpeg_path || '未找到'}\nyt-dlp：${status.value.ytdlp}\nN_m3u8DL-RE：${status.value.n_m3u8dl || '未安装'}\n路径：${status.value.n_m3u8dl_path || '-'}\nCookie：${status.value.cookie_source || 'none'}\n扩展目录：${status.value.extension_dir || '-'}`,
            '环境检测',
            { confirmButtonText: '确定' }
          );
        }

        async function updateWhisper() {
          updatingWhisper.value = true;
          try {
            const model = (settings.value.whisper_model || 'base');
            const r = await api('/api/update/whisper', { method: 'POST', body: JSON.stringify({ model }) });
            ElementPlus.ElMessage.success(r.message || '已开始安装 Whisper');
            setTimeout(loadStatus, 8000);
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          } finally {
            updatingWhisper.value = false;
          }
        }
        async function updateNm3u8() {
          updatingNm3u8.value = true;
          try {
            const r = await api('/api/update/n_m3u8dl', { method: 'POST' });
            ElementPlus.ElMessage.success(r.message || '已开始下载 N_m3u8DL-RE');
            setTimeout(loadStatus, 12000);
          } catch (e) {
            ElementPlus.ElMessage.error(e.message);
          } finally {
            updatingNm3u8.value = false;
          }
        }

        function downloadExtension() {
          window.open('/api/extension/zip', '_blank');
          ElementPlus.ElMessage.info('正在下载扩展 ZIP。Chrome：开发者模式 → 加载已解压扩展（先解压 ZIP）；Firefox：about:debugging → 临时载入 → 选 manifest.json');
        }

        async function updateYtdlp() {
          updatingYtdlp.value = true;
          try {
            const r = await api('/api/update/ytdlp', { method: 'POST' });
            ElementPlus.ElMessage.success(r.message || '已开始更新 yt-dlp');
            setTimeout(loadStatus, 8000);
          } catch (e) {
            ElementPlus.ElMessage.error(e.message);
          } finally {
            updatingYtdlp.value = false;
          }
        }

        async function updateFfmpeg() {
          updatingFfmpeg.value = true;
          try {
            const r = await api('/api/update/ffmpeg', { method: 'POST' });
            ElementPlus.ElMessage.success(r.message || '已开始更新 FFmpeg');
            setTimeout(loadStatus, 15000);
          } catch (e) {
            ElementPlus.ElMessage.error(e.message);
          } finally {
            updatingFfmpeg.value = false;
          }
        }

        function verCmp(a, b) {
          // 「2026.8.19 (local)」「未安装」这类带尾巴/中文的写法都要能比：只取第一段数字串逐段比
          const seg = (s) => {
            const m = String(s || '').match(/\d+(?:\.\d+)*/);
            return m ? m[0].split('.').map(Number) : [];
          };
          const x = seg(a);
          const y = seg(b);
          // 一侧根本没有版本号（如「未安装」）时，有版本号的那一侧就是更新的
          if (!x.length) return y.length ? -1 : 0;
          if (!y.length) return 1;
          for (let i = 0; i < Math.max(x.length, y.length); i++) {
            const d = (x[i] || 0) - (y[i] || 0);
            if (d) return d > 0 ? 1 : -1;
          }
          return 0;
        }

        const askedLatest = ref(false);
        async function loadComponents(withLatest) {
          if (withLatest) latestBusy.value = true;
          if (withLatest) askedLatest.value = true;
          try {
            const d = await api('/api/components' + (askedLatest.value ? '?latest=1' : ''));
            components.value = d.items || [];
            compInfo.value = d || {};
            applyCompCheck(d.update_check);
          } catch (e) {
            ElementPlus.ElMessage.error('组件状态读取失败: ' + e.message);
          } finally {
            if (withLatest) latestBusy.value = false;
          }
        }

        /* ---- 组件上游版本自动检测：查询在后端后台线程跑，界面读状态、缺一次就补发 ---- */
        const COMP_POPUP_KEY = 'mdCompUpdatePopupShown';
        const compUpdates = ref([]);   // 确有可更新版本的组件；未安装的和查不到上游版的都不算
        const compCheckAt = ref('');
        const compCheckError = ref('');
        const compCheckBusy = ref(false);
        let compPopupShown = false;

        function navDot(k) {
          if (k !== 'settings' || !compUpdates.value.length) return '';
          return compUpdates.value.length + ' 个组件有可更新版本，见「设置 → 组件与依赖」';
        }

        const compCheckText = computed(() => {
          if (compCheckBusy.value) return '正在联网查询上游最新版本…';
          if (compCheckError.value) return '上次检测失败：' + compCheckError.value;
          if (!compCheckAt.value) return '尚未检测上游版本';
          const at = compCheckAt.value.slice(5);  // 去掉年份，界面里只留「月-日 时:分:秒」
          if (!compUpdates.value.length) return `最近检测 ${at}：已在用组件都是最新版本`;
          const names = compUpdates.value.map((u) => u.label.split('（')[0]);
          const shown = names.slice(0, 3).join('、') + (names.length > 3 ? ` 等 ${names.length} 项` : '');
          return `最近检测 ${at}：${shown} 有可更新版本，点各行可逐项更新`;
        });

        // 自动检测已经拿到最新版，直接补进表格的「最新」列，不用再点一次「查询上游最新版本」
        function mergeCompLatest() {
          const map = {};
          (compUpdates.value || []).forEach((u) => { map[u.key] = u.latest; });
          (components.value || []).forEach((it) => { if (!it.latest && map[it.key]) it.latest = map[it.key]; });
        }

        function applyCompCheck(st) {
          if (!st) return;
          compUpdates.value = st.available || [];
          compCheckAt.value = st.finished || '';
          compCheckError.value = st.error || '';
          mergeCompLatest();
        }

        async function fetchCompCheck() {
          const d = await api('/api/components/update-check', { noLog: true });
          applyCompCheck(d);
          return d;
        }

        // 一次查询要两三秒，界面每 1.5 秒读一次状态，最多等 90 秒（后端还在跑，下次打开能看到）
        async function waitCompCheck() {
          for (let i = 0; i < 60; i++) {
            await new Promise((r) => setTimeout(r, 1500));
            try {
              const d = await fetchCompCheck();
              if (d.status !== 'running') return d;
            } catch (_) { return null; }
          }
          return null;
        }

        async function startCompCheck(fromUser) {
          compCheckBusy.value = true;
          let d = null;
          try {
            d = await api('/api/components/update-check', {
              method: 'POST',
              body: JSON.stringify({ force: !!fromUser }),
              noLog: !fromUser,
              uiName: fromUser ? '组件与依赖：点「立即检测」联网查询上游版本' : undefined,
            });
            applyCompCheck(d);
            if (d.status === 'running') d = await waitCompCheck();
            if (fromUser) {
              if (!d) ElementPlus.ElMessage.warning('上游版本查询未在预期时间内返回，可稍后再点「立即检测」');
              else if (compCheckError.value) ElementPlus.ElMessage.error('检测失败：' + compCheckError.value);
              else if (compUpdates.value.length) {
                ElementPlus.ElMessage.success(`检测完成：${compUpdates.value.length} 个组件有可更新版本`);
              } else ElementPlus.ElMessage.success('检测完成：已在用组件都是最新版本');
            }
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
            compCheckBusy.value = false;
            return;
          }
          compCheckBusy.value = false;
          if (d && (fromUser || d.auto_check)) maybePopupCompUpdates(fromUser);
        }

        function maybePopupCompUpdates(fromUser) {
          if (!compUpdates.value.length) return;
          if (!fromUser) {
            // 自动检测每次浏览器会话只弹一次，之后靠侧栏「设置」上的橙点提醒，不再打扰
            if (compPopupShown) return;
            compPopupShown = true;
            try {
              if (sessionStorage.getItem(COMP_POPUP_KEY)) return;
              sessionStorage.setItem(COMP_POPUP_KEY, '1');
            } catch (_) {}
          }
          const rows = compUpdates.value.map((u) => `<li><b>${escHtml(u.label)}</b>：`
            + `${escHtml(u.current)} → ${escHtml(u.latest)}</li>`);
          ElementPlus.ElMessageBox.confirm(
            `<div style="margin-bottom:6px">以下组件有可更新版本：</div>`
            + `<ul style="margin:0;padding-left:18px;line-height:1.7">${rows.join('')}</ul>`
            + `<div style="margin-top:8px">进入「设置 → 组件与依赖」后可逐项更新，或点「一键更新」批量处理。`
            + `未安装的组件不计入本提醒；FFmpeg 与 N_m3u8DL-RE 不在 PyPI，查不到它们的最新版。</div>`,
            `${compUpdates.value.length} 个组件有可更新版本`,
            { dangerouslyUseHTMLString: true, confirmButtonText: '去组件与依赖', cancelButtonText: '稍后', type: 'warning' }
          ).then(() => {
            logAction('弹窗跳转：设置 → 组件与依赖');
            page.value = 'settings';
            // 切页时 .content 正在放 translateY 入场动画，这段时间里 smooth 滚动会被浏览器静默丢弃，只用瞬时滚动
            setTimeout(() => {
              const el = document.getElementById('comp-card');
              if (el) el.scrollIntoView({ block: 'start' });
            }, 120);
          }).catch(() => {});
        }

        async function bootCompCheck() {
          try {
            let d = await fetchCompCheck();
            if (d.status === 'idle' && d.auto_check) {
              // 开关开着但后端那次没跑起来（比如刚把开关打开）：这里补发一次，查询本身在后台
              d = await api('/api/components/update-check', {
                method: 'POST', body: JSON.stringify({ force: false }), noLog: true,
              });
              applyCompCheck(d);
            }
            if (d.status === 'running') d = await waitCompCheck();
            if (d && d.auto_check) maybePopupCompUpdates(false);
          } catch (_) {}
        }

        async function setEnvPath(action) {
          pathBusy.value = true;
          try {
            const r = await api('/api/env/path', { method: 'POST', body: JSON.stringify({ action }) });
            if (r.ok) ElementPlus.ElMessage.success(r.message || '已处理');
            else ElementPlus.ElMessage.error(r.message || '操作失败');
            compInfo.value = Object.assign({}, compInfo.value, { env_path: r.env_path || compInfo.value.env_path });
            await loadComponents();
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          } finally {
            pathBusy.value = false;
          }
        }

        const compToolRunners = {
          ytdlp: () => updateYtdlp(),
          ffmpeg: () => updateFfmpeg(),
          n_m3u8dl: () => updateNm3u8(),
          'faster-whisper': () => updateWhisper(),
        };

        async function updateComponent(it) {
          // 先静默保存：镜像填在设置里，不保存后端读不到
          try { await saveSettings(true); } catch (_) {}
          const runner = compToolRunners[it.key];
          if (runner) {
            await runner();
          } else {
            updatingComp.value = it.key;
            try {
              const r = await api('/api/update/pkg', {
                method: 'POST',
                body: JSON.stringify({ name: it.key, mirror: settings.value.pip_mirror || '' }),
              });
              ElementPlus.ElMessage.success(r.message || (it.key + ' 更新已开始'));
            } catch (e) {
              ElementPlus.ElMessage.error(String(e.message || e));
            } finally {
              updatingComp.value = '';
            }
          }
          setTimeout(() => { loadComponents(); loadStatus(); }, 25000);
        }

        const compAllBusy = ref(false);
        let compAllTimer = null;
        const compAll = computed(() => compInfo.value.update_all || {});
        // 待处理 = 没装上的 + 查过最新版且确实有新版的；没点过「查询上游最新版本」时只挑缺的
        const compTargets = computed(() => (components.value || []).filter(
          // skip_all：PO Token 那行缺的是要自己跑的服务端，一键更新替人装插件没意义
          (it) => !it.skip_all && (!it.ok || (it.latest && verCmp(it.latest, it.active) > 0))));
        const compAllSummary = computed(() => {
          const a = compAll.value;
          const rs = a.results || [];
          if (a.running) {
            return `一键更新进行中（第 ${(a.done || 0) + 1} / ${a.total || 0} 项：${a.current || '-'}），进度详见「运行日志」。`;
          }
          if (!rs.length) return '';
          const bad = rs.filter((r) => !r.ok);
          const head = `上次一键更新（${a.started || '-'}）：成功 ${rs.length - bad.length} / ${rs.length}`;
          if (!bad.length) return `${head}，全部成功。`;
          return `${head}；未成功的：${bad.map((r) => `${r.label}（${r.msg || '原因见运行日志'}）`).join('；')}。`;
        });

        function stopCompAllPoll() {
          if (compAllTimer) { clearInterval(compAllTimer); compAllTimer = null; }
        }

        function startCompAllPoll() {
          stopCompAllPoll();
          compAllTimer = setInterval(async () => {
            await loadComponents();
            if (!compAll.value.running) {
              stopCompAllPoll();
              loadStatus();
            }
          }, 5000);
        }

        async function updateAllComponents() {
          const list = compTargets.value;
          if (!list.length) {
            ElementPlus.ElMessage.info(compInfo.value.latest_checked
              ? '没有需要更新的条目：表内组件均已就绪，且已是查询到的最新版。'
              : '目前只能挑出「未安装」的条目。要先按最新版补齐，请点「查询上游最新版本」。');
            return;
          }
          try { await saveSettings(true); } catch (_) {}
          const rows = list.map((it) => (it.ok
            ? `<li>更新 <b>${escHtml(it.label)}</b>：${escHtml(it.active || '?')} → ${escHtml(it.latest)}</li>`
            : `<li>安装 <b>${escHtml(it.label)}</b>（当前：${escHtml(it.active || '未安装')}）</li>`));
          try {
            await ElementPlus.ElMessageBox.confirm(
              `<ul style="margin:0;padding-left:18px">${rows.join('')}</ul>`
              + `<div style="margin-top:8px">按上表顺序一项一项进行，期间请勿关闭程序。`
              + `工具走「网络与并发」里的 GitHub 镜像，Python 依赖走 pip 镜像；`
              + `含 faster-whisper 时会连同模型一起下载，可能耗时较久且占用数百 MB。</div>`,
              '一键更新组件与依赖',
              { dangerouslyUseHTMLString: true, confirmButtonText: '开始更新', cancelButtonText: '取消' }
            );
          } catch (_) { return; }
          compAllBusy.value = true;
          try {
            const r = await api('/api/components/update-all', {
              method: 'POST',
              body: JSON.stringify({ keys: list.map((it) => it.key), mirror: settings.value.pip_mirror || '' }),
            });
            if (r.ok === false) { ElementPlus.ElMessage.warning(r.message || '未能开始更新'); return; }
            ElementPlus.ElMessage.success(r.message || '一键更新已在后台开始');
            await loadComponents();
            startCompAllPoll();
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          } finally {
            compAllBusy.value = false;
          }
        }

        onUnmounted(stopCompAllPoll);

        async function loadConfig() {
          try {
            const data = await api('/api/config');
            opts.value.download_dir = data.download_dir || '';
            opts.value.video_quality = data.video_quality || 'best';
            opts.value.audio_quality = data.audio_quality || 'best';
            opts.value.format = data.format || 'mkv';
            opts.value.embed_sub = data.embed_sub !== false;
            opts.value.write_sub_files = data.write_sub_files !== false;
            opts.value.audio_only = !!data.audio_only;
            const raw = data.subtitle_langs || 'zh-Hans,zh-CN,zh,zh-Hant,zh-TW';
            opts.value.subtitle_langs = raw;
            const known = new Set(subLangOptions.map(i => i.value));
            subLangList.value = raw.split(',').map(s => s.trim()).filter(s => s && known.has(s));
            if (!subLangList.value.length) {
              subLangList.value = ['zh-Hans', 'zh-CN', 'zh', 'zh-Hant', 'zh-TW'];
            }
            settings.value.proxy = data.proxy || '';
            settings.value.proxy_mode = ['auto', 'always', 'none'].includes(data.proxy_mode) ? data.proxy_mode : 'auto';
            const pbp = data.proxy_by_platform || {};
            settings.value.proxy_by_platform = Object.fromEntries(
              Object.keys(pbp).filter(k => typeof pbp[k] === 'boolean').map(k => [k, pbp[k]])
            );
            settings.value.nocheckcertificate = data.nocheckcertificate !== false;
            settings.value.concurrent = data.concurrent || 3;
            settings.value.download_dir = data.download_dir || '';
            settings.value.cookie_source = data.cookie_source || 'none';
            settings.value.cookie_browser = data.cookie_browser || 'chrome';
            settings.value.cookie_file = data.cookie_file || '';
            settings.value.ffmpeg_path = data.ffmpeg_path || '';
            settings.value.video_encoder = ['auto', 'cpu', 'nvidia', 'intel', 'amd'].includes(data.video_encoder) ? data.video_encoder : 'cpu';
            settings.value.video_cpu_codec = ['x264', 'x265'].includes(data.video_cpu_codec) ? data.video_cpu_codec : 'x264';
            settings.value.video_cpu_preset = ['veryfast', 'fast', 'medium', 'slow'].includes(data.video_cpu_preset) ? data.video_cpu_preset : 'medium';
            settings.value.speed_limit = data.speed_limit || '';
            settings.value.global_speed_limit = data.global_speed_limit || '';
            settings.value.speed_windows = data.speed_windows || '';
            settings.value.run_window = data.run_window || '';
            settings.value.queue_windows = Object.assign({}, data.queue_windows || {});
            settings.value.ytdlp_extra_args = data.ytdlp_extra_args || '';
            settings.value.max_per_host = data.max_per_host != null ? data.max_per_host : 2;
            settings.value.adaptive_throttle = data.adaptive_throttle !== false;
            settings.value.plugins_enabled = data.plugins_enabled !== false;
            settings.value.aria2_enabled = !!data.aria2_enabled;
            settings.value.aria2_rpc = data.aria2_rpc || 'http://127.0.0.1:6800/jsonrpc';
            settings.value.aria2_secret = data.aria2_secret || '';
            settings.value.aria2_for_large_mb = data.aria2_for_large_mb != null ? data.aria2_for_large_mb : 50;
            settings.value.aria2_bin = data.aria2_bin || '';
            settings.value.aria2_autostart = data.aria2_autostart !== false;
            settings.value.torrent_seed_ratio = data.torrent_seed_ratio != null ? data.torrent_seed_ratio : 1;
            settings.value.torrent_seed_time = data.torrent_seed_time != null ? data.torrent_seed_time : 3600;
            settings.value.torrent_meta_timeout = data.torrent_meta_timeout != null ? data.torrent_meta_timeout : 180;
            settings.value.bt_trackers = data.bt_trackers || '';
            settings.value.bt_tracker_sources = data.bt_tracker_sources || '';
            settings.value.bt_tracker_auto_update = data.bt_tracker_auto_update !== false;
            settings.value.bt_tracker_max = data.bt_tracker_max != null ? data.bt_tracker_max : 30;
            settings.value.bt_dl_limit = data.bt_dl_limit || '';
            settings.value.bt_ul_limit = data.bt_ul_limit || '';
            settings.value.bt_prioritize_piece = !!data.bt_prioritize_piece;
            settings.value.bt_auto_rules = (Array.isArray(data.bt_auto_rules) ? data.bt_auto_rules : []).map(r => ({
              name: r.name || '',
              mode: r.mode === 'regex' ? 'regex' : 'contains',
              pattern: r.pattern || '',
              subdir: r.subdir || '',
              enabled: r.enabled !== false,
            }));
            settings.value.bt_auto_fallback = data.bt_auto_fallback || '';
            settings.value.http_impersonate = data.http_impersonate !== false;
            settings.value.yt_player_clients = data.yt_player_clients || 'default,web_safari,tv,android,ios';
            settings.value.po_provider_enabled = !!data.po_provider_enabled;
            settings.value.po_provider_url = data.po_provider_url || 'http://127.0.0.1:4416';
            settings.value.github_mirror = data.github_mirror != null ? data.github_mirror : 'https://ghproxy.net/';
            settings.value.pip_mirror = data.pip_mirror != null ? data.pip_mirror : 'https://pypi.tuna.tsinghua.edu.cn/simple';
            settings.value.sub_first_download_n = data.sub_first_download_n || 0;
            settings.value.local_ai_transcribe = !!data.local_ai_transcribe;
            settings.value.local_ai_translate = !!data.local_ai_translate;
            settings.value.local_ai_lang = data.local_ai_lang || 'zh';
            settings.value.whisper_model = data.whisper_model || 'base';
            settings.value.whisper_device = data.whisper_device || 'auto';
            settings.value.whisper_compute = data.whisper_compute || 'auto';
            settings.value.diarization_enabled = !!data.diarization_enabled;
            settings.value.diarization_max_speakers = Math.min(8, Math.max(2, parseInt(data.diarization_max_speakers, 10) || 4));
            settings.value.hf_token = data.hf_token || '';
            settings.value.local_ai_mt_after_transcribe = !!data.local_ai_mt_after_transcribe;
            settings.value.subtitle_translate_provider = data.subtitle_translate_provider || 'deepl';
            settings.value.subtitle_target_lang = data.subtitle_target_lang || 'zh';
            settings.value.subtitle_glossary = data.subtitle_glossary || '';
            settings.value.subtitle_wrap = data.subtitle_wrap !== false;
            settings.value.subtitle_wrap_width = data.subtitle_wrap_width || 16;
            settings.value.subtitle_wrap_lines = Math.min(4, Math.max(1, parseInt(data.subtitle_wrap_lines, 10) || 3));
            settings.value.subtitle_qc = data.subtitle_qc !== false;
            settings.value.subtitle_qc_reflect = !!data.subtitle_qc_reflect;
            settings.value.subtitle_export_set = data.subtitle_export_set || 'single';
            checkGlossary(true);
            settings.value.deepl_api_key = data.deepl_api_key || '';
            settings.value.deepl_api_url = data.deepl_api_url || '';
            settings.value.openai_api_key = data.openai_api_key || '';
            settings.value.acoustid_api_key = data.acoustid_api_key || '';
            settings.value.acoustid_min_score = data.acoustid_min_score != null ? data.acoustid_min_score : 0.5;
            settings.value.openai_base_url = data.openai_base_url || 'https://api.openai.com/v1';
            settings.value.openai_model = data.openai_model || 'gpt-4o-mini';
            settings.value.anthropic_api_key = data.anthropic_api_key || '';
            settings.value.anthropic_model = data.anthropic_model || 'claude-sonnet-4-20250514';
            settings.value.gemini_api_key = data.gemini_api_key || '';
            settings.value.gemini_model = data.gemini_model || 'gemini-2.0-flash';
            settings.value.google_translate_api_key = data.google_translate_api_key || '';
            settings.value.azure_translator_key = data.azure_translator_key || '';
            settings.value.azure_translator_region = data.azure_translator_region || 'eastasia';
            settings.value.azure_translator_endpoint = data.azure_translator_endpoint || 'https://api.cognitive.microsofttranslator.com';
            settings.value.filename_template = data.filename_template || '%(title).80B [%(id)s].%(ext)s';
            settings.value.write_description = !!data.write_description;
            settings.value.write_info_json = !!data.write_info_json;
            settings.value.write_sub_files = data.write_sub_files !== false;
            settings.value.dark_mode = !!data.dark_mode;
            settings.value.telegram_enabled = !!data.telegram_enabled;
            settings.value.telegram_bot_token = data.telegram_bot_token || '';
            settings.value.telegram_chat_id = data.telegram_chat_id || '';
            settings.value.telegram_notify_done = data.telegram_notify_done !== false;
            settings.value.telegram_notify_fail = data.telegram_notify_fail !== false;
            settings.value.telegram_notify_sub = data.telegram_notify_sub !== false;
            settings.value.telegram_commands_enabled = data.telegram_commands_enabled !== false;
            settings.value.sub_interval_min = data.sub_interval_min || 60;
            settings.value.sub_auto_download = data.sub_auto_download !== false;
            settings.value.live_from_start = data.live_from_start !== false;
            settings.value.live_max_minutes = Math.max(0, Math.min(1440, Number(data.live_max_minutes || 0)));
            settings.value.live_stream_fallback = data.live_stream_fallback !== false;
            settings.value.live_stream_pref_bilibili = data.live_stream_pref_bilibili || 'flv';
            settings.value.live_stream_pref_youtube = data.live_stream_pref_youtube || 'dash';
            settings.value.live_stream_pref_douyin = data.live_stream_pref_douyin || 'hls';
            settings.value.live_stream_pref_twitch = data.live_stream_pref_twitch || 'hls';
            settings.value.live_stream_pref_default = data.live_stream_pref_default || 'auto';
            settings.value.serverchan_sendkey = data.serverchan_sendkey || '';
            settings.value.wecom_enabled = !!data.wecom_enabled;
            settings.value.wecom_corp_id = data.wecom_corp_id || '';
            settings.value.wecom_corp_secret = data.wecom_corp_secret || '';
            settings.value.wecom_agent_id = data.wecom_agent_id || '';
            settings.value.wecom_touser = data.wecom_touser || '@all';
            settings.value.wecom_notify_done = !!data.wecom_notify_done;
            settings.value.wecom_notify_fail = !!data.wecom_notify_fail;
            settings.value.wecom_notify_sub = !!data.wecom_notify_sub;
            settings.value.storage_post_action = data.storage_post_action || 'none';
            settings.value.storage_nas_enabled = !!data.storage_nas_enabled;
            settings.value.storage_nas_path = data.storage_nas_path || '';
            settings.value.storage_webdav_enabled = !!data.storage_webdav_enabled;
            settings.value.storage_webdav_url = data.storage_webdav_url || '';
            settings.value.storage_webdav_user = data.storage_webdav_user || '';
            settings.value.storage_webdav_pass = data.storage_webdav_pass || '';
            settings.value.storage_webdav_path = data.storage_webdav_path || '/';
            settings.value.risk_preset = data.risk_preset || 'standard';
            settings.value.risk_delay_sec = data.risk_delay_sec != null ? data.risk_delay_sec : 1;
            settings.value.concurrent_fragments = data.concurrent_fragments || 4;
            settings.value.sub_scan_delay_sec = data.sub_scan_delay_sec || 10;
            settings.value.risk_cooldown_429 = data.risk_cooldown_429 || 60;
            settings.value.risk_user_agent = data.risk_user_agent || '';
            settings.value.ui_theme = data.ui_theme || 'blue';
            settings.value.web_auth_enabled = !!data.web_auth_enabled;
            settings.value.web_auth_session_hours = Math.max(1, Math.min(720, Number(data.web_auth_session_hours) || 12));
            settings.value.web_auth_remember_days = Math.max(1, Math.min(365, Number(data.web_auth_remember_days) || 30));
            settings.value.web_auth_max_fails = Math.max(1, Math.min(50, Number(data.web_auth_max_fails) || 5));
            settings.value.web_auth_lock_minutes = Math.max(1, Math.min(1440, Number(data.web_auth_lock_minutes) || 15));
            applyDark(settings.value.dark_mode);
            applyTheme(settings.value.ui_theme);
          } catch (_) {}
        }

        function applyDark(on) {
          document.body.classList.toggle('dark', !!on);
        }
        function toggleDark() {
          settings.value.dark_mode = !settings.value.dark_mode;
          applyDark(settings.value.dark_mode);
          logAction(settings.value.dark_mode ? '切换为深色模式' : '切换为浅色模式');
        }
        const UI_THEMES = [
          { key: 'blue', name: '年度蓝', en: 'Luminous Blue' },
          { key: 'orange', name: '活力橘', en: 'Energy Orange' },
          { key: 'pink', name: '流行粉', en: 'Pop Pink' },
          { key: 'green', name: '草地绿', en: 'Meadowland Green' },
          { key: 'clay', name: '陶土色', en: 'Clay' },
        ];
        function applyTheme(name) {
          document.body.dataset.theme = UI_THEMES.some(t => t.key === name) ? name : 'blue';
        }
        function setTheme(name) {
          settings.value.ui_theme = name;
          applyTheme(name);
          const t = UI_THEMES.find(x => x.key === name);
          logAction('切换主题为「' + ((t && t.name) || name) + '」');
        }
        async function openDownloadFolder() {
          try {
            await api('/api/open-folder', { method: 'POST', body: JSON.stringify({ path: filesPath.value || '' }) });
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '打开失败');
          }
        }
        async function testCookie() {
          try {
            const data = await api('/api/test-cookie', { method: 'POST', body: '{}' });
            if (data.ok) ElementPlus.ElMessage.success(data.message);
            else ElementPlus.ElMessage.warning(data.message);
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '检测失败');
          }
        }
        async function loadSubs() {
          try {
            const data = await api('/api/subs');
            subs.value = data.subs || [];
            subMusicHosts.value = data.music_hosts || [];
          } catch (_) {}
        }
        async function addSub() {
          const list = subLines(subUrl.value);
          if (!list.length) {
            ElementPlus.ElMessage.warning('需 http 链接（含 RSS 源完整地址），或 Telegram 频道（@名称 / t.me/名称 / t.me/c/内部 id）');
            return;
          }
          subAdding.value = true;
          const bad = [];
          let ok = 0, seen = 0;
          for (const u of list) {
            const kind = subKindOfUrl(u);
            try {
              const r = await api('/api/subs/add', {
                method: 'POST',
                body: JSON.stringify({
                  url: u, mode: kind === 'tg' ? subMode.value : '', kind,
                  auto_download: !!subAutoAdd.value,
                }),
              });
              ok++;
              seen += (r && r.init_count) || 0;
            } catch (e) {
              bad.push(`${u.replace(/^https?:\/\//, '').slice(0, 40)}：${e.message || '加不进去'}`);
            }
          }
          subUrl.value = bad.join('\n');
          try {
            await loadSubs();
          } catch (_) {}
          subAdding.value = false;
          const tail = bad.length ? `，${bad.length} 条失败（原因已保留在输入框中）` : '';
          if (ok && !bad.length) {
            ElementPlus.ElMessage.success(seen
              ? `已添加 ${ok} 条，已保留原有 ${seen} 条记录（未下载任何内容）；此后每轮仅处理最新未读`
              : `已添加 ${ok} 条订阅`);
          } else if (ok) {
            ElementPlus.ElMessage.warning(`已添加 ${ok} 条${tail}`);
          } else {
            ElementPlus.ElMessage.error(bad[0] || '添加失败');
          }
        }
        async function removeSub(s) {
          try {
            await ElementPlus.ElMessageBox.confirm('删除该订阅？', '确认', { type: 'warning' });
            await api('/api/subs/remove', { method: 'POST', body: JSON.stringify({ id: s.id }) });
            await loadSubs();
          } catch (_) {}
        }
        async function toggleSub(s, v) {
          await api('/api/subs/toggle', { method: 'POST', body: JSON.stringify({ id: s.id, enabled: v }) });
          await loadSubs();
        }
        async function setSubAuto(s, v) {
          try {
            await api('/api/subs/rules', {
              method: 'POST', body: JSON.stringify({ id: s.id, rules: s.rules || {}, auto_download: !!v }),
            });
            s.auto_download = !!v;
            ElementPlus.ElMessage.success(v ? `「${s.title}」新增条目将自动下载` : `「${s.title}」仅列出新增，不再加入队列`);
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '修改失败');
          }
        }
        async function scanOneSub(s) {
          subBusy.value = s.id;
          try {
            const r = await api('/api/subs/scan-one', { method: 'POST', body: JSON.stringify({ id: s.id }) });
            const err = (r.item && r.item.last_error) || '';
            if (err) ElementPlus.ElMessage.warning('读取失败：' + err);
            else ElementPlus.ElMessage.success(`最新未读 ${r.new || 0} 条 · 按规则[${r.rules_text || '默认'}]`);
            await loadSubs();
            await loadTasks();
          } catch (e) {
            ElementPlus.ElMessage.error(e.message);
          } finally {
            subBusy.value = '';
          }
        }
        function openSubBackfill(s) {
          const r = s.rules || {};
          backfillRange.value = r.since || r.until ? [r.since || '', r.until || ''] : [];
          backfillSub.value = s;
        }
        function closeSubBackfill() { backfillSub.value = null; }
        async function runSubBackfill() {
          const s = backfillSub.value;
          const rg = backfillRange.value || [];
          if (!s) return;
          // 音乐歌单不标每首歌的收录日期：这类订阅的回填＝补下整张歌单里目录中还没有的歌
          const noDate = s.kind === 'music';
          if (!noDate && (!rg[0] || !rg[1])) {
            ElementPlus.ElMessage.warning('回填需填写完整的起止日期，否则与直接扫描无差异');
            return;
          }
          backfilling.value = true;
          try {
            const r = await api('/api/subs/backfill', {
              method: 'POST', body: JSON.stringify({ id: s.id, since: rg[0] || '', until: rg[1] || '' }),
            });
            await loadSubs();
            await loadTasks();
            backfillSub.value = subs.value.find((x) => x.id === s.id) || backfillSub.value;
            if (r.last_error) ElementPlus.ElMessage.warning('读取失败：' + r.last_error);
            else if (noDate) {
              ElementPlus.ElMessage[r.new ? 'success' : 'info'](r.new
                ? `按规则[${r.rules_text || '默认'}]从歌单里选了 ${r.new} 首，下载目录里已有的会自动跳过，进度见音乐页与运行日志`
                : '这张歌单没有符合规则的曲目，具体原因见运行日志');
            }
            else if (!r.new) ElementPlus.ElMessage.info(`${rg[0]} ~ ${rg[1]} 内无可下载条目 — 请查看规则或运行日志中的原因`);
            else ElementPlus.ElMessage.success(`窗口内命中 ${r.new} 条，已按规则[${r.rules_text || '默认'}]加入队列；若仍有截断，可再次点击回填`);
          } catch (e) {
            ElementPlus.ElMessage.error(e.message);
          } finally {
            backfilling.value = false;
          }
        }
        async function scanAllSubs() {
          subScanning.value = true;
          try {
            const r = await api('/api/subs/scan', { method: 'POST', body: '{}' });
            ElementPlus.ElMessage.success(`检查 ${r.checked} 源，新增 ${r.new}`);
            await loadSubs();
            await loadTasks();
          } catch (e) {
            ElementPlus.ElMessage.error(e.message);
          } finally {
            subScanning.value = false;
          }
        }
        async function openSubPlan(s) {
          subPlanSub.value = s;
          subPlan.value = null;
          subPlanArch.value = [];
          const el = document.getElementById('sub-plan-card');
          if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
          await loadSubPlan();
        }
        function closeSubPlan() {
          subPlanSub.value = null;
          subPlan.value = null;
          subPlanArch.value = [];
        }
        async function loadSubPlan() {
          const s = subPlanSub.value;
          if (!s) return;
          subPlanLoading.value = true;
          try {
            const r = await api('/api/subs/preview', { method: 'POST', body: JSON.stringify({ id: s.id }) });
            subPlan.value = r.plan || null;
            const a = await api('/api/subs/archived', { method: 'POST', body: JSON.stringify({ id: s.id }) });
            subPlanArch.value = (a && a.items) || [];
            if (subPlan.value && subPlan.value.error) ElementPlus.ElMessage.warning('这一轮没法计算：' + subPlan.value.error);
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '预览失败');
          } finally {
            subPlanLoading.value = false;
          }
        }
        async function runSubPlanNow() {
          const s = subPlanSub.value;
          if (!s) return;
          await scanOneSub(s);
          const cur = subs.value.find((x) => x.id === s.id);
          if (cur) subPlanSub.value = cur;
          await loadSubPlan();
        }
        async function clearSubArchive(item) {
          const s = subPlanSub.value;
          if (!s) return;
          try {
            await ElementPlus.ElMessageBox.confirm(item ? '不再留档这一条？' : '清空这条订阅的上游删除留档？',
              '确认', { type: 'warning' });
          } catch (_) { return; }
          try {
            const r = await api('/api/subs/archived/clear', {
              method: 'POST',
              body: JSON.stringify({ id: s.id, entry_id: item ? (item.id || '') : '' }),
            });
            ElementPlus.ElMessage.success(r.removed ? `已移除 ${r.removed} 条留档记录（不影响「已读过」游标）`
              : '没有需要移除的留档记录');
            await loadSubs();
            await loadSubPlan();
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '移除失败');
          }
        }

        const subRuleQualities = ['best', '4K', '1440p', '1080p', '720p', '480p', '360p'];
        const subRuleFormats = ['mkv', 'mp4', 'webm', 'mp3', 'm4a', 'flac'];
        const ruleSub = ref(null);
        const ruleSaving = ref(false);
        const ruleForm = ref({
          types: [], only_kw: '', skip_kw: '', min_min: 0, max_min: 0, audio_only: false,
          video_quality: 'follow', format: 'follow', run_ai: 'follow', filename_template: '', max_per_scan: 20,
          range: [], mode: '', auto_download: true, download_dir: '',
        });
        const ruleSubIsTg = computed(() => (ruleSub.value || {}).kind === 'tg');
        // 音乐歌单只按「筛歌」类规则办事：画质 / 封装 / 仅音频 / 目录 / 命名是 yt-dlp 那条路的选项，
        // 音乐成品沿用音乐搜索页的模板与音质设置，套在这里只会让人以为改了就会生效。
        const ruleSubIsMusic = computed(() => (ruleSub.value || {}).kind === 'music');
        function openSubRules(s) {
          const r = s.rules || {};
          ruleForm.value = {
            types: (r.types || []).slice(),
            only_kw: (r.only_kw || []).join(','),
            skip_kw: (r.skip_kw || []).join(','),
            min_min: Math.round((r.min_dur || 0) / 60),
            max_min: Math.round((r.max_dur || 0) / 60),
            audio_only: !!r.audio_only,
            video_quality: r.video_quality || 'follow',
            format: r.format || 'follow',
            run_ai: r.run_ai || 'follow',
            filename_template: r.filename_template || '',
            max_per_scan: r.max_per_scan === undefined || r.max_per_scan === null ? 20 : r.max_per_scan,
            range: r.since || r.until ? [r.since || '', r.until || ''] : [],
            mode: s.mode || '',
            auto_download: s.auto_download !== false,
            download_dir: r.download_dir || '',
          };
          ruleSub.value = s;
        }
        function closeSubRules() { ruleSub.value = null; }
        async function saveSubRules() {
          const s = ruleSub.value;
          if (!s) return;
          const f = ruleForm.value;
          if (f.min_min && f.max_min && f.max_min < f.min_min) {
            ElementPlus.ElMessage.warning('时长上限需大于下限');
            return;
          }
          const tpl = (f.filename_template || '').trim();
          if (tpl && !tpl.includes('%(ext)s')) {
            ElementPlus.ElMessage.warning('命名模板结尾需保留 %(ext)s，否则下载的文件缺少扩展名');
            return;
          }
          const rules = {
            types: f.types || [],
            only_kw: f.only_kw || '',
            skip_kw: f.skip_kw || '',
            min_dur: (Number(f.min_min) || 0) * 60,
            max_dur: (Number(f.max_min) || 0) * 60,
            audio_only: !!f.audio_only,
            video_quality: f.video_quality,
            format: f.format,
            run_ai: f.run_ai,
            filename_template: tpl,
            max_per_scan: Number(f.max_per_scan) || 0,
            since: (f.range && f.range[0]) || '',
            until: (f.range && f.range[1]) || '',
            download_dir: (f.download_dir || '').trim(),
          };
          ruleSaving.value = true;
          try {
            const r = await api('/api/subs/rules', {
              method: 'POST',
              body: JSON.stringify({ id: s.id, rules, mode: f.mode || '', auto_download: !!f.auto_download }),
            });
            ElementPlus.ElMessage.success('规则已保存：' + (r.rules_text || ''));
            await loadSubs();
            ruleSub.value = subs.value.find((x) => x.id === s.id) || null;
          } catch (e) {
            ElementPlus.ElMessage.error(e.message);
          } finally {
            ruleSaving.value = false;
          }
        }
        
        async function loadLiveMonitors() {
          try {
            const data = await api('/api/live/monitors');
            liveMonitors.value = data.monitors || [];
          } catch (_) {}
        }
        async function addLiveMonitor() {
          const u = (liveMonitorUrl.value || '').trim();
          if (!u.startsWith('http')) {
            ElementPlus.ElMessage.warning('请输入直播间链接');
            return;
          }
          try {
            await api('/api/live/monitors/add', { method: 'POST', body: JSON.stringify({ url: u }) });
            liveMonitorUrl.value = '';
            ElementPlus.ElMessage.success('已添加监控');
            await loadLiveMonitors();
          } catch (e) {
            ElementPlus.ElMessage.error(e.message);
          }
        }
        async function removeLiveMonitor(m) {
          await api('/api/live/monitors/remove', { method: 'POST', body: JSON.stringify({ id: m.id }) });
          await loadLiveMonitors();
        }
        async function pauseLiveMonitor(m) {
          await api('/api/live/monitors/pause', { method: 'POST', body: JSON.stringify({ id: m.id, url: m.url }) });
          ElementPlus.ElMessage.info('已暂停该房间自动录制');
          await loadLiveMonitors();
        }
        async function resumeLiveMonitor(m) {
          await api('/api/live/monitors/resume', { method: 'POST', body: JSON.stringify({ id: m.id, url: m.url }) });
          ElementPlus.ElMessage.success('已恢复自动录制');
          await loadLiveMonitors();
          await loadTasks();
        }
        async function scanLiveMonitors() {
          try {
            const r = await api('/api/live/monitors/scan', { method: 'POST', body: '{}' });
            ElementPlus.ElMessage.success('检测完成，新开播 ' + (r.started || 0) + ' 路');
            await loadLiveMonitors();
            await loadTasks();
          } catch (e) {
            ElementPlus.ElMessage.error(e.message);
          }
        }
        function openLiveMonitorCfg(m) {
          if (!m) return;
          liveRoomCfg.value = {
            visible: true,
            saving: false,
            id: m.id,
            url: m.url,
            fmt: m.fmt || '',
            video_quality: m.video_quality || '',
            auto_transcode: m.auto_transcode || '',
            max_minutes: Number(m.max_minutes || 0),
            win_start: m.win_start || '',
            win_end: m.win_end || '',
          };
        }
        async function saveLiveMonitorCfg() {
          const c = liveRoomCfg.value;
          c.saving = true;
          try {
            const r = await api('/api/live/monitors/set', {
              method: 'POST',
              body: JSON.stringify({
                id: c.id,
                fmt: c.fmt,
                video_quality: c.video_quality,
                auto_transcode: c.auto_transcode,
                max_minutes: c.max_minutes,
                win_start: c.win_start,
                win_end: c.win_end,
              }),
            });
            const notes = (r && r.notes) || [];
            if (notes.length) {
              // 合法的那几项后端已经落库，这里只点名没采用的，弹窗留着让人改
              ElementPlus.ElMessage.warning('已保存，其中 ' + notes.length + ' 项设置没生效：'
                + notes.slice(0, 3).join('；') + (notes.length > 3 ? ' 等' : ''));
              await loadLiveMonitors();
            } else {
              ElementPlus.ElMessage.success('已保存');
              c.visible = false;
              await loadLiveMonitors();
            }
          } catch (e) {
            ElementPlus.ElMessage.error(e.message);
          } finally {
            c.saving = false;
          }
        }
        function liveMonitorCfgText(m) {
          if (!m) return '';
          const parts = [];
          if (m.fmt) parts.push('封装 ' + m.fmt);
          if (m.video_quality) parts.push('画质 ' + m.video_quality);
          const mm = Number(m.max_minutes || 0);
          const gd = Number(settings.value.live_max_minutes || 0);
          if (mm > 0) parts.push('录满 ' + mm + ' 分钟自动停');
          else if (gd > 0) parts.push('录满 ' + gd + ' 分钟自动停（默认）');
          if (m.auto_transcode) {
            const p = (transcodePresets.value || []).find(x => x.id === m.auto_transcode);
            parts.push('录完转 ' + (p ? p.label : m.auto_transcode));
          }
          if (m.win_start && m.win_end) parts.push('只在 ' + m.win_start + '–' + m.win_end + ' 监控');
          return parts.length ? '本房间：' + parts.join(' · ') : '';
        }

        
        async function pauseLiveTask(t) {
          if (!t) return;
          await api('/api/pause', { method: 'POST', body: JSON.stringify({ ids: [t.id] }) });
          await loadTasks();
        }
        async function resumeLiveTask(t) {
          if (!t) return;
          await api('/api/resume', { method: 'POST', body: JSON.stringify({ ids: [t.id] }) });
          await loadTasks();
        }

        async function pollBrowserSniff() {
          try {
            const r = await api('/api/sniff/browser/status');
            browserSniff.value = r;
          } catch (e) {}
        }
        async function startBrowserSniff(mode) {
          browserSniffLoading.value = true;
          try {
            const r = await api('/api/sniff/browser/start', {
              method: 'POST',
              body: JSON.stringify({
                mode: mode || 'launch',
                port: browserSniffPort.value || 9222,
                url: (sniffUrl.value || '').trim() || 'about:blank',
              }),
            });
            browserSniff.value = r;
            ElementPlus.ElMessage.success(
              mode === 'attach' ? '已连接浏览器' : '已启动托管浏览器，请打开目标页并播放'
            );
            if (browserSniffTimer) clearInterval(browserSniffTimer);
            browserSniffTimer = setInterval(pollBrowserSniff, 1500);
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '启动失败');
          } finally {
            browserSniffLoading.value = false;
          }
        }
        async function stopBrowserSniff() {
          try {
            const r = await api('/api/sniff/browser/stop', { method: 'POST', body: '{}' });
            browserSniff.value = r;
            if (browserSniffTimer) {
              clearInterval(browserSniffTimer);
              browserSniffTimer = null;
            }
            ElementPlus.ElMessage.info('已停止监听');
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '停止失败');
          }
        }
        async function clearBrowserSniff() {
          try {
            await api('/api/sniff/browser/clear', { method: 'POST', body: '{}' });
            await pollBrowserSniff();
          } catch (e) {}
          sniffItems.value = [];
          sniffSelected.value = [];
        }
        async function runSniff() {
          const u = (sniffUrl.value || '').trim();
          if (!u) { ElementPlus.ElMessage.warning('请输入网页链接'); return; }
          sniffLoading.value = true;
          sniffDone.value = false;
          sniffSelected.value = [];
          try {
            const r = await api('/api/sniff', { method: 'POST', body: JSON.stringify({ url: u }) });
            sniffItems.value = r.items || [];
            sniffDone.value = true;
            ElementPlus.ElMessage.success('发现 ' + (r.count || 0) + ' 条');
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '嗅探失败');
          } finally {
            sniffLoading.value = false;
          }
        }
        function sniffSelectAll() {
          sniffSelected.value = sniffDisplayItems.value.map(x => x.url);
        }
        function sniffSelectNone() { sniffSelected.value = []; }
        async function sniffDownloadSelected() {
          if (!sniffSelected.value.length) return;
          await api('/api/sniff/download', { method: 'POST', body: JSON.stringify({ urls: sniffSelected.value }) });
          ElementPlus.ElMessage.success('已加入下载队列');
          page.value = 'queue';
          await loadTasks();
        }
        async function sniffDownloadOne(it) {
          await api('/api/sniff/download', { method: 'POST', body: JSON.stringify({ urls: [it.url] }) });
          ElementPlus.ElMessage.success('已加入下载队列');
        }
        async function sniffDownloadMerge() {
          if (!canSniffMerge.value) {
            ElementPlus.ElMessage.warning('请各勾选 1 条 video（或 hls/dash）和 1 条 audio');
            return;
          }
          const selected = sniffDisplayItems.value.filter(it => sniffSelected.value.includes(it.url));
          const video = selected.find(it => ['video', 'hls', 'dash', 'direct'].includes((it.kind || '').toLowerCase()));
          const audio = selected.find(it => (it.kind || '').toLowerCase() === 'audio');
          if (!video || !audio) return;
          sniffMergeLoading.value = true;
          try {
            const title = (video.title || audio.title || '').replace(/\s*\[\d+.*$/, '').trim() || 'merged';
            await api('/api/sniff/download_merge', {
              method: 'POST',
              body: JSON.stringify({
                video_url: video.url,
                audio_url: audio.url,
                title,
              }),
            });
            ElementPlus.ElMessage.success('已加入合并下载队列');
            page.value = 'queue';
            await loadTasks();
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '合并下载失败');
          } finally {
            sniffMergeLoading.value = false;
          }
        }

        /* ---- 接收猫抓（cat-catch）推送 ---- */
        const catcatchFileInput = ref(null);
        const catcatch = reactive({ endpoint: '', bodyTemplate: '', rules: [], stat: {}, keys_waiting: 0 });
        async function loadCatcatch() {
          try {
            const r = await api('/api/catcatch/status');
            catcatch.endpoint = r.endpoint || '';
            catcatch.bodyTemplate = r.body_template || '';
            catcatch.rules = r.rules || [];
            catcatch.stat = r.stat || {};
            catcatch.keys_waiting = r.keys_waiting || 0;
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '读取猫抓接收状态失败');
          }
        }
        function triggerCatcatchImport() {
          if (catcatchFileInput.value) catcatchFileInput.value.click();
        }
        async function onCatcatchConfig(ev) {
          const f = ev.target.files && ev.target.files[0];
          if (!f) return;
          try {
            const r = await api('/api/catcatch/import-config', {
              method: 'POST',
              body: JSON.stringify({ text: await f.text() }),
            });
            let msg = `猫抓正则规则共 ${r.found} 条：新增 ${r.added}，重复跳过 ${r.duplicated}`;
            if ((r.invalid || []).length) {
              msg += `，${r.invalid.length} 条在本机编译不过已跳过（第一条：${r.invalid[0].reason}）`;
            }
            ElementPlus.ElMessage.success(msg);
            await loadCatcatch();
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '导入失败');
          }
          ev.target.value = '';
        }
        async function toggleCatcatchRule(i) {
          try {
            const r = await api('/api/catcatch/rules/toggle', { method: 'POST', body: JSON.stringify({ index: i }) });
            catcatch.rules = r.rules || [];
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '操作失败');
          }
        }
        async function deleteCatcatchRule(i) {
          try {
            const r = await api('/api/catcatch/rules/delete', { method: 'POST', body: JSON.stringify({ index: i }) });
            catcatch.rules = r.rules || [];
            ElementPlus.ElMessage.success('已删除该规则');
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '删除失败');
          }
        }
        async function clearCatcatchRules() {
          try {
            await api('/api/catcatch/rules/clear', { method: 'POST', body: '{}' });
            await loadCatcatch();
            ElementPlus.ElMessage.success('已清空猫抓规则');
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '清空失败');
          }
        }

        function copyText(t) {
          navigator.clipboard.writeText(t || '').then(() => ElementPlus.ElMessage.success('已复制')).catch(() => {});
        }
        async function loadLibrary(force) {
          libraryLoading.value = true;
          if (force) libQa.value = {};
          try {
            const r = force
              ? await api('/api/library/scan', { method: 'POST', body: '{}' })
              : await api('/api/library');
            libraryItems.value = (r.items || []).map(x => ({ ...x, _preset: 'mp4', _tc: false }));
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '扫描失败');
          } finally {
            libraryLoading.value = false;
          }
        }
        async function loadTranscodePresets() {
          try {
            const r = await api('/api/transcode/presets');
            transcodePresets.value = r.presets || [];
          } catch (e) {}
        }
        async function runTranscode(it) {
          if (!it._preset) { ElementPlus.ElMessage.warning('请选择预设'); return; }
          it._tc = true;
          try {
            const r = await api('/api/transcode', {
              method: 'POST',
              body: JSON.stringify({ path: it.path, preset: it._preset, delete_source: false }),
            });
            ElementPlus.ElMessage.success('转码完成: ' + (r.name || ''));
            await loadLibrary(true);
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '转码失败');
          } finally {
            it._tc = false;
          }
        }
        async function openLibFolder(it) {
          try {
            await api('/api/open-folder', { method: 'POST', body: JSON.stringify({ path: it.path }) });
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '打开失败');
          }
        }
        async function endLiveTask(t) {
          if (!t) return;
          try {
            await api('/api/live/end', { method: 'POST', body: JSON.stringify({ ids: [t.id] }) });
            ElementPlus.ElMessage.success('已结束录制，文件保留在下载目录');
            await loadTasks();
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '结束失败');
          }
        }
        async function endAllLive() {
          try {
            const r = await api('/api/live/end', { method: 'POST', body: JSON.stringify({ ids: [] }) });
            ElementPlus.ElMessage.success('已结束 ' + (r.count || 0) + ' 个直播录制');
            await loadTasks();
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '结束失败');
          }
        }
        async function cancelLiveTask(t) {
          if (!t) return;
          try {
            await ElementPlus.ElMessageBox.confirm('取消并移除任务？已录片段仍保留在下载目录。', '确认', { type: 'warning' });
          } catch (_) { return; }
          await api('/api/live/end', { method: 'POST', body: JSON.stringify({ ids: [t.id] }) }).catch(() => {});
          await api('/api/tasks/delete', { method: 'POST', body: JSON.stringify({ ids: [t.id] }) });
          await loadTasks();
          ElementPlus.ElMessage.info('已取消并移除任务');
        }

        async function startLiveRecord() {
          const u = (liveUrl.value || '').trim();
          if (!u.startsWith('http')) {
            ElementPlus.ElMessage.warning('请输入直播链接');
            return;
          }
          submitting.value = true;
          try {
            const mm = Math.max(0, Math.min(1440, Number(liveRecordMinutes.value || 0)));
            await api('/api/download', {
              method: 'POST',
              body: JSON.stringify({
                urls: [u],
                ...opts.value,
                is_live: true,
                live_max_minutes: mm,
                skip_downloaded: false,
                allow_playlist: false,
              }),
            });
            ElementPlus.ElMessage.success(mm > 0
              ? `已加入直播录制队列，录满 ${mm} 分钟自动结束并保存`
              : '已加入直播录制队列，' + (Number(settings.value.live_max_minutes || 0) > 0
                  ? `录满 ${settings.value.live_max_minutes} 分钟自动结束并保存`
                  : '将录制到手动结束'));
            await loadTasks();
            // 留在直播页查看进行中任务
          } catch (e) {
            ElementPlus.ElMessage.error(e.message);
          } finally {
            submitting.value = false;
          }
        }
        async function testTelegram() {
          tgTesting.value = true;
          try {
            // 先保存设置再测试
            await saveSettings(true);
            await api('/api/telegram/test', { method: 'POST', body: '{}' });
            ElementPlus.ElMessage.success('测试消息已发送');
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '发送失败');
          } finally {
            tgTesting.value = false;
          }
        }
        async function testWecom() {
          wecomTesting.value = true;
          try {
            await saveSettings(true);
            await api('/api/wecom/test', { method: 'POST', body: '{}' });
            ElementPlus.ElMessage.success('企业微信测试消息已发送');
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '发送失败');
          } finally {
            wecomTesting.value = false;
          }
        }
        async function testStorage() {
          storageTesting.value = true;
          try {
            await saveSettings(true);
            const r = await api('/api/storage/test', { method: 'POST', body: '{}' });
            const msgs = [];
            if (r.nas) msgs.push(r.nas.ok ? ('NAS OK: ' + (r.nas.path || '')) : ('NAS 失败: ' + friendlyError(r.nas.error || '')));
            if (r.webdav) msgs.push(r.webdav.ok ? ('WebDAV OK HTTP ' + r.webdav.status) : ('WebDAV 失败: ' + friendlyError(r.webdav.error || '')));
            if (!msgs.length) ElementPlus.ElMessage.warning('请先启用 NAS 或 WebDAV');
            else if (msgs.some(m => m.includes('失败'))) ElementPlus.ElMessage.error(msgs.join(' | '));
            else ElementPlus.ElMessage.success(msgs.join(' | '));
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '测试失败');
          } finally {
            storageTesting.value = false;
          }
        }
        async function applyRiskPreset(key) {
          try {
            const r = await api('/api/risk/preset', { method: 'POST', body: JSON.stringify({ preset: key }) });
            settings.value.risk_preset = key;
            const p = (r && r.applied) || {};
            if (p.risk_delay_sec != null) settings.value.risk_delay_sec = p.risk_delay_sec;
            if (p.risk_cooldown_429 != null) settings.value.risk_cooldown_429 = p.risk_cooldown_429;
            if (p.sub_scan_delay_sec != null) settings.value.sub_scan_delay_sec = p.sub_scan_delay_sec;
            ElementPlus.ElMessage.success('已应用风控档位：' + (riskPresets.value[key]?.label || key));
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '应用失败');
          }
        }
        async function loadRiskPresets() {
          try {
            const r = await api('/api/risk/presets');
            if (r.presets) riskPresets.value = r.presets;
            if (r.current) settings.value.risk_preset = r.current;
          } catch (_) {}
        }
        /* 收藏页统一入口：接口返回的 total 可能大于实际取回的条数，区分「上限截断」和「失效条目」 */
        const FAV_TAB_NAMES = {
          folders: 'B站收藏夹', toview: 'B站稍后再看', followings: 'B站关注',
          yt_liked: 'YouTube 我喜欢', yt_wl: 'YouTube 稍后再看', yt_pl: 'YouTube 播放列表',
        };
        function applyFavList(r) {
          favItems.value = (r && r.items) || [];
          const total = (r && (r.media_count || r.total)) || favItems.value.length;
          favMeta.value = {
            total,
            truncated: !!(r && r.partial),
            missing: Math.max(0, total - favItems.value.length),
          };
          logAction(`加载${FAV_TAB_NAMES[favTab.value] || '收藏列表'}：取回 ${favItems.value.length} 条（平台记录 ${total} 条）`);
        }
        async function loadFavTab() {
          favLoading.value = true;
          favItems.value = [];
          favSelected.value = [];
          favMeta.value = { total: 0, truncated: false, missing: 0 };
          try {
            if (favTab.value === 'folders') {
              const r = await api('/api/favorites/bili/folders');
              favFolders.value = r.folders || [];
              if (!favFolderId.value && favFolders.value.length) {
                favFolderId.value = favFolders.value[0].id;
              }
              if (favFolderId.value) await loadFavFolderItems();
            } else if (favTab.value === 'toview') {
              const r = await api('/api/favorites/bili/toview');
              applyFavList(r);
            } else if (favTab.value === 'followings') {
              const r = await api('/api/favorites/bili/followings?fetch_all=true');
              applyFavList(r);
            } else if (favTab.value === 'yt_liked') {
              const r = await api('/api/favorites/youtube/liked?limit=200');
              applyFavList(r);
            } else if (favTab.value === 'yt_wl') {
              const r = await api('/api/favorites/youtube/watchlater?limit=200');
              applyFavList(r);
            } else if (favTab.value === 'yt_pl') {
              if (ytPlaylistUrl.value) await loadYtPlaylist();
            }
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '加载失败（请检查对应平台 Cookie）');
          } finally {
            favLoading.value = false;
          }
        }
        async function loadYtPlaylist() {
          const u = (ytPlaylistUrl.value || '').trim();
          if (!u) {
            ElementPlus.ElMessage.warning('请粘贴 YouTube 播放列表链接');
            return;
          }
          favLoading.value = true;
          try {
            const r = await api('/api/favorites/youtube/playlist?url=' + encodeURIComponent(u) + '&limit=200');
            applyFavList(r);
            if (!favItems.value.length) ElementPlus.ElMessage.info('列表为空');
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '加载播放列表失败');
          } finally {
            favLoading.value = false;
          }
        }
        async function loadFavFolderItems() {
          if (!favFolderId.value) return;
          favLoading.value = true;
          favSelected.value = [];
          try {
            const r = await api('/api/favorites/bili/folder-items?media_id=' + encodeURIComponent(favFolderId.value) + '&fetch_all=true');
            applyFavList(r);
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '加载收藏夹失败');
          } finally {
            favLoading.value = false;
          }
        }
        function onFavSelChange(rows) { favSelected.value = rows || []; }
        async function downloadFavSelected() {
          const urls = favSelected.value.map(x => x.url).filter(Boolean);
          if (!urls.length) return;
          try {
            const r = await api('/api/favorites/download', { method: 'POST', body: JSON.stringify({ urls }) });
            ElementPlus.ElMessage.success('已加入下载：' + (r.count || urls.length));
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '下载失败');
          }
        }
        async function downloadFavOne(row) {
          if (!row || !row.url) return;
          try {
            await api('/api/favorites/download', { method: 'POST', body: JSON.stringify({ urls: [row.url] }) });
            ElementPlus.ElMessage.success('已加入下载');
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '失败');
          }
        }
        async function subscribeFavSelected() {
          for (const row of favSelected.value) {
            if (row.url) {
              try { await api('/api/subs/add', { method: 'POST', body: JSON.stringify({ url: row.url, title: row.title || '' }) }); } catch (_) {}
            }
          }
          ElementPlus.ElMessage.success('已提交订阅');
        }
        async function subscribeFavOne(row) {
          if (!row || !row.url) return;
          try {
            await api('/api/subs/add', { method: 'POST', body: JSON.stringify({ url: row.url, title: row.title || '' }) });
            ElementPlus.ElMessage.success('已订阅');
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '订阅失败');
          }
        }
        async function startBiliQr() {
          biliQrLoading.value = true;
          biliQrMsg.value = '';
          biliQrImage.value = '';
          try {
            const r = await api('/api/bili/qr/generate');
            biliQrUrl.value = r.url || '';
            biliQrKey.value = r.qrcode_key || '';
            biliQrImage.value = r.qr_image || '';
            biliQrMsg.value = '请使用哔哩哔哩 App 扫描上方二维码，然后点「检查扫码状态」';
            // 若后端未生成图片，尝试用第三方 API 生成（需联网）
            if (!biliQrImage.value && biliQrUrl.value) {
              biliQrImage.value = 'https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=' + encodeURIComponent(biliQrUrl.value);
            }
            // 自动轮询几次
            if (biliQrKey.value) {
              let n = 0;
              const timer = setInterval(async () => {
                n += 1;
                try {
                  const pr = await api('/api/bili/qr/poll', { method: 'POST', body: JSON.stringify({ qrcode_key: biliQrKey.value }) });
                  biliQrMsg.value = pr.message || '';
                  if (pr.ok) {
                    clearInterval(timer);
                    ElementPlus.ElMessage.success('登录成功，Cookie 已保存');
                    await loadPlatformCookies();
                  } else if (pr.status === 'expired' || n >= 40) {
                    clearInterval(timer);
                    if (pr.status === 'expired') ElementPlus.ElMessage.warning('二维码已过期，请重新获取');
                  }
                } catch (_) {
                  if (n >= 40) clearInterval(timer);
                }
              }, 3000);
            }
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '获取二维码失败');
          } finally {
            biliQrLoading.value = false;
          }
        }
        async function pollBiliQr() {
          if (!biliQrKey.value) return;
          try {
            const r = await api('/api/bili/qr/poll', { method: 'POST', body: JSON.stringify({ qrcode_key: biliQrKey.value }) });
            biliQrMsg.value = r.message || '';
            if (r.ok) {
              ElementPlus.ElMessage.success('登录成功，Cookie 已保存');
              await loadPlatformCookies();
            } else if (r.status === 'expired') {
              ElementPlus.ElMessage.warning('二维码已过期，请重新获取');
            }
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '检查失败');
          }
        }
        function isPlayable(row) {
          const e = (row.ext || '').toLowerCase();
          return VIDEO_EXTS.includes(e) || AUDIO_EXTS.includes(e) || ['.jpg', '.jpeg', '.png', '.gif', '.webp'].includes(e);
        }
        function isAudioFile(row) {
          const n = ((row && (row.name || row.path)) || '').toLowerCase();
          return /\.(mp3|flac|m4a|ogg|wav|aac|wma|opus)$/.test(n);
        }
        async function openPicard(row) {
          try {
            await api('/api/music/tag', { method: 'POST', body: JSON.stringify({ path: row.path, use_picard: true }) });
            ElementPlus.ElMessage.success('已尝试打开 Picard');
          } catch (e) { ElementPlus.ElMessage.error(String(e.message || e)); }
        }
        async function fingerprintFile(row) {
          try {
            const r = await api('/api/music/fingerprint', {
              method: 'POST',
              body: JSON.stringify({ path: row.path, apply_tags: true }),
            });
            if (r.ok === false) ElementPlus.ElMessage.error(r.message || '指纹识别未启动');
            else ElementPlus.ElMessage.success(r.message || '指纹识别已开始');
          } catch (e) { ElementPlus.ElMessage.error(String(e.message || e)); }
        }
        async function guessTagsFile(row) {
          try {
            const r = await api('/api/music/guess_tags', {
              method: 'POST',
              body: JSON.stringify({ path: row.path, apply: true }),
            });
            ElementPlus.ElMessage.success(r.message || JSON.stringify(r.guess || {}));
          } catch (e) { ElementPlus.ElMessage.error(String(e.message || e)); }
        }
        async function mbEnrichFile(row) {
          try {
            const title = (row.name || '').replace(/\.[^.]+$/, '');
            const r = await api('/api/music/mb_enrich', {
              method: 'POST',
              body: JSON.stringify({ path: row.path, title }),
            });
            ElementPlus.ElMessage.success(r.message || '已开始 MB 匹配');
          } catch (e) { ElementPlus.ElMessage.error(String(e.message || e)); }
        }
        async function mbTagFile(row) {
          try {
            const title = (row.name || '').replace(/\.[^.]+$/, '');
            const r = await api('/api/music/mb_lookup', { method: 'POST', body: JSON.stringify({ title }) });
            const hit = (r.items || [])[0];
            if (!hit) { ElementPlus.ElMessage.warning('MusicBrainz 无匹配'); return; }
            await api('/api/music/tag', {
              method: 'POST',
              body: JSON.stringify({
                path: row.path,
                title: hit.title,
                artists: hit.artists,
                album: hit.album,
              }),
            });
            ElementPlus.ElMessage.success('已按 MusicBrainz 写入: ' + (hit.title || ''));
          } catch (e) { ElementPlus.ElMessage.error(String(e.message || e)); }
        }
        function isMediaFile(row) {
          const e = (row.ext || (row.name || '').split('.').pop() || '').toLowerCase().replace(/^\.?/, '.');
          const name = (row.name || '').toLowerCase();
          const ext = e.startsWith('.') ? e : '.' + e;
          return ['.mp4','.mkv','.webm','.flv','.mov','.ts','.m4a','.mp3','.wav','.aac'].includes(ext)
            || /\.(mp4|mkv|webm|flv|mov|ts|m4a|mp3|wav|aac)$/i.test(name);
        }
        function isSrtFile(row) {
          const name = (row.name || '').toLowerCase();
          return name.endsWith('.srt');
        }
        function isVideoFile(row) {
          const name = (row.name || '').toLowerCase();
          return VIDEO_EXTS.some((e) => name.endsWith(e));
        }
        function onFileSelectionChange(rows) {
          selectedFiles.value = rows || [];
        }
        async function runBatchAi() {
          batchRunning.value = true;
          try {
            const body = {
              mode: batchMode.value || 'transcribe',
              lang: settings.value.local_ai_lang || 'auto',
              provider: settings.value.subtitle_translate_provider || 'deepl',
              target_lang: settings.value.subtitle_target_lang || 'zh',
              source_lang: settings.value.local_ai_lang || '',
            };
            if (batchScope.value === 'selected') {
              const paths = (selectedFiles.value || []).map((r) => r.path).filter(Boolean);
              if (!paths.length) {
                ElementPlus.ElMessage.warning('请先勾选文件');
                return;
              }
              body.paths = paths;
            } else {
              // 当前目录绝对路径 = filesRoot + filesPath
              const folder = [filesRoot.value, filesPath.value].filter(Boolean).join('/').replace(/\\/g, '/');
              if (!folder && !filesRoot.value) {
                ElementPlus.ElMessage.warning('无法确定目录');
                return;
              }
              body.folder = filesRoot.value && filesPath.value
                ? (filesRoot.value.replace(/[\\/]$/, '') + '/' + filesPath.value.replace(/^[/\\]/, '')).replace(/\\/g, '/')
                : (filesRoot.value || filesPath.value);
            }
            const r = await api('/api/ai/batch', { method: 'POST', body: JSON.stringify(body) });
            ElementPlus.ElMessage.success(r.message || `已开始 ${r.count || ''} 个文件`);
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          } finally {
            batchRunning.value = false;
          }
        }
        async function runSrtCalibrateSelected() {
          const paths = (selectedFiles.value || [])
            .filter((r) => (r.name || '').toLowerCase().endsWith('.srt'))
            .map((r) => r.path);
          if (!paths.length) {
            ElementPlus.ElMessage.warning('请勾选 .srt 文件');
            return;
          }
          let ok = 0;
          for (const path of paths) {
            try {
              await api('/api/ai/srt_calibrate', {
                method: 'POST',
                body: JSON.stringify({
                  path,
                  offset_sec: syncOffsetSec.value || 0,
                  scale: syncScale.value || 1,
                  inplace: !!syncInplace.value,
                }),
              });
              ok += 1;
            } catch (e) {
              ElementPlus.ElMessage.error(`${path}: ${e.message || e}`);
            }
          }
          ElementPlus.ElMessage.success(`已校准 ${ok}/${paths.length} 个字幕`);
          loadFiles(filesPath.value);
        }
        async function aiCalibrateSrt(row) {
          try {
            const { value } = await ElementPlus.ElMessageBox.prompt(
              '输入平移秒数（负=提前，正=延后）。可写如 -1.5',
              '时间轴校准',
              { inputValue: String(syncOffsetSec.value || 0), confirmButtonText: '校准' }
            );
            const sec = parseFloat(value);
            if (Number.isNaN(sec)) {
              ElementPlus.ElMessage.error('请输入数字');
              return;
            }
            const r = await api('/api/ai/srt_calibrate', {
              method: 'POST',
              body: JSON.stringify({
                path: row.path,
                offset_sec: sec,
                scale: syncScale.value || 1,
                inplace: !!syncInplace.value,
              }),
            });
            ElementPlus.ElMessage.success(r.message || '已校准');
            loadFiles(filesPath.value);
          } catch (e) {
            if (e !== 'cancel' && e !== 'close') ElementPlus.ElMessage.error(String(e.message || e));
          }
        }

        async function exportBilingual(row) {
          try {
            const r = await api('/api/ai/subtitle_export', {
              method: 'POST',
              body: JSON.stringify({ path: row.path }),
            });
            ElementPlus.ElMessage.success(r.message || '已导出');
            loadFiles(filesPath.value);
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          }
        }

        async function exportBilingualSelected() {
          const srts = (selectedFiles.value || []).filter(
            (r) => /\.srt$/i.test(r.name || '') && !/\.bi\./i.test(r.name || '')
          );
          if (!srts.length) {
            ElementPlus.ElMessage.warning('请先勾选 .srt 文件（已生成的 .bi. 文件请排除）');
            return;
          }
          let ok = 0;
          const skipped = [];
          for (const row of srts) {
            try {
              await api('/api/ai/subtitle_export', { method: 'POST', body: JSON.stringify({ path: row.path }) });
              ok += 1;
            } catch (e) {
              skipped.push(`${row.name}: ${e.message || e}`);
            }
          }
          if (ok) ElementPlus.ElMessage.success(`已导出 ${ok} 组双语字幕${skipped.length ? `，${skipped.length} 个跳过` : ''}`);
          if (skipped.length) ElementPlus.ElMessage.warning(skipped[0]);
          loadFiles(filesPath.value);
        }
        
        const burnDlg = ref({ row: null, srt: '', fontsize: 44, position: 'bottom', font: 'Microsoft YaHei', crf: 20, overwrite: false });
        const burnJob = ref(null);
        const burnStarting = ref(false);
        let burnTimer = null;

        const burnSubChoices = computed(() =>
          (fileItems.value || []).filter((r) => !r.is_dir && /\.(srt|ass|vtt)$/i.test(r.name || ''))
        );
        const burnOutName = computed(() =>
          (burnDlg.value.row ? String(burnDlg.value.row.name).replace(/\.[^.]+$/, '') : '') + '.hardsub.mp4'
        );
        const burnRunning = computed(() => !!burnJob.value && burnJob.value.status === 'running');
        const burnPercent = computed(() => {
          const j = burnJob.value || {};
          const total = Number(j.total) || 0;
          const p = String(j.elapsed || '').split(':');
          if (!total || p.length !== 3) return 0;
          const done = (Number(p[0]) || 0) * 3600 + (Number(p[1]) || 0) * 60 + (Number(p[2]) || 0);
          return Math.max(0, Math.min(99, Math.round((done / total) * 100)));
        });
        const burnStatusText = computed(() => {
          const j = burnJob.value;
          if (!j) return '';
          if (j.status === 'running') {
            return `进行中 ${j.elapsed || '…'}${j.total ? ' / ' + Math.round(j.total) + 's' : ''} · ${j.message || ''}`;
          }
          return j.message || '';
        });

        function openBurn(row) {
          burnDlg.value.row = row;
          burnDlg.value.srt = '';
          burnJob.value = null;
          revealCard('card-file-burn');
          fetchBurnJobs();
          if (!burnTimer) burnTimer = setInterval(pollBurn, 1500);
        }
        function closeBurn() {
          burnDlg.value.row = null;
          burnJob.value = null;
          if (burnTimer) { clearInterval(burnTimer); burnTimer = null; }
        }
        function applyBurnJobs(jobs) {
          const row = burnDlg.value.row;
          if (!row) return;
          const prev = burnJob.value && burnJob.value.status;
          const job = (jobs || []).find((j) => j.media === row.path) || null;
          burnJob.value = job;
          if (!job || prev === job.status) return;
          if (job.status === 'done') {
            ElementPlus.ElMessage.success(job.message || '字幕烧录已完成');
            loadFiles(filesPath.value);
          } else if (job.status === 'failed') {
            ElementPlus.ElMessage.error(job.message || '字幕烧录失败，详见运行日志');
          } else if (job.status === 'stopped') {
            loadFiles(filesPath.value);
          }
        }
        async function fetchBurnJobs() {
          try {
            applyBurnJobs((await api('/api/ai/hardsub_jobs')).jobs || []);
          } catch (e) {}
        }
        function pollBurn() {
          if (!sseOn.value) fetchBurnJobs();  // SSE 正常时 hardsub 帧会自己推过来
        }
        async function startBurn() {
          const row = burnDlg.value.row;
          if (!row) return;
          const d = burnDlg.value;
          burnStarting.value = true;
          try {
            const r = await api('/api/ai/hardsub', {
              method: 'POST',
              body: JSON.stringify({
                path: row.path, srt: d.srt, fontsize: d.fontsize, position: d.position,
                font: d.font, crf: d.crf, overwrite: d.overwrite,
              }),
            });
            ElementPlus.ElMessage.success(r.message || '开始烧录字幕');
            burnJob.value = { media: row.path, out: r.out, status: 'running', elapsed: '', total: 0, message: '准备中' };
            pollBurn();
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          } finally {
            burnStarting.value = false;
          }
        }
        async function stopBurn() {
          const row = burnDlg.value.row;
          if (!row) return;
          try {
            await api('/api/ai/hardsub_stop', { method: 'POST', body: JSON.stringify({ path: row.path }) });
            ElementPlus.ElMessage.info('已请求停止，未完成的文件将被删除');
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          }
        }

        function pipelineBody(path, only) {
          return {
            path,
            subtitle_first: settings.value.subtitle_first !== false,
            polish: !!settings.value.ai_polish,
            summarize: !!settings.value.ai_summarize,
            translate: !!settings.value.local_ai_mt_after_transcribe,
            lang: settings.value.local_ai_lang || 'auto',
            summary_lang: settings.value.summary_lang || 'zh',
            target_lang: settings.value.subtitle_target_lang || 'zh',
            only: only || '',
          };
        }

        const PIPELINE_STATUS = {
          done: { label: '已完成', type: 'success' },
          running: { label: '进行中', type: 'warning' },
          failed: { label: '失败', type: 'danger' },
          skipped: { label: '跳过', type: 'info' },
          pending: { label: '未开始', type: 'info' },
        };
        function pipeStatusLabel(s) { return (PIPELINE_STATUS[s] || PIPELINE_STATUS.pending).label; }
        function pipeStatusType(s) { return (PIPELINE_STATUS[s] || PIPELINE_STATUS.pending).type; }

        async function refreshPipeline(row, showLoading) {
          if (!row) return;
          try {
            pipelineView.value = await api('/api/ai/pipeline_status?path=' + encodeURIComponent(row.path));
            const running = (pipelineView.value.stages || []).some((s) => s.status === 'running');
            if (running && !pipelineTimer) {
              pipelineTimer = setInterval(() => refreshPipeline(pipelineRow.value), 4000);
            } else if (!running && pipelineTimer) {
              clearInterval(pipelineTimer);
              pipelineTimer = null;
              if (showLoading) loadFiles(filesPath.value);
            }
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          }
        }

        function showPipeline(row) {
          pipelineRow.value = row;
          pipelineView.value = { stages: [], updated: '' };
          revealCard('card-file-pipeline');
          refreshPipeline(row, true);
        }

        function closePipeline() {
          if (pipelineTimer) { clearInterval(pipelineTimer); pipelineTimer = null; }
          pipelineRow.value = null;
          pipelineView.value = null;
        }

        async function rerunStage(name) {
          const row = pipelineRow.value;
          if (!row) return;
          try {
            const r = await api('/api/ai/pipeline', {
              method: 'POST',
              body: JSON.stringify(pipelineBody(row.path, name)),
            });
            ElementPlus.ElMessage.success(r.message || '已启动');
            refreshPipeline(row);
          } catch (e) { ElementPlus.ElMessage.error(String(e.message || e)); }
        }

        async function aiPipeline(row) {
          try {
            const r = await api('/api/ai/pipeline', {
              method: 'POST',
              body: JSON.stringify(pipelineBody(row.path, '')),
            });
            ElementPlus.ElMessage.success(r.message || '流水线已启动');
            showPipeline(row);
          } catch (e) { ElementPlus.ElMessage.error(String(e.message || e)); }
        }
        async function analyzeAudioFile(row) {
          try {
            const r = await api('/api/ai/analyze', {
              method: 'POST',
              body: JSON.stringify({ path: row.path, write_json: true }),
            });
            if (r.ok === false) ElementPlus.ElMessage.error(r.message || '音频分析未启动');
            else ElementPlus.ElMessage.success(r.message || '分析已开始，见日志');
          } catch (e) { ElementPlus.ElMessage.error(String(e.message || e)); }
        }
        async function aiDemucs(row) {
          try {
            await api('/api/ai/demucs', { method: 'POST', body: JSON.stringify({ path: row.path }) });
            ElementPlus.ElMessage.success('Demucs 分离中，见日志与 demucs/ 目录');
          } catch (e) { ElementPlus.ElMessage.error(String(e.message || e)); }
        }
        async function aiTts(row) {
          try {
            await api('/api/ai/tts', { method: 'POST', body: JSON.stringify({ path: row.path, voice: settings.value.edge_tts_voice }) });
            ElementPlus.ElMessage.success('Edge-TTS 合成中');
          } catch (e) { ElementPlus.ElMessage.error(String(e.message || e)); }
        }
        async function installVoicePkgs() {
          installingVoice.value = true;
          try {
            const r = await api('/api/ai/install_voice', { method: 'POST', body: JSON.stringify({ pkg: 'all' }) });
            ElementPlus.ElMessage.success(r.message || '安装中');
            loadVoiceStatus();
          } catch (e) { ElementPlus.ElMessage.error(String(e.message || e)); }
          finally { installingVoice.value = false; }
        }
        async function loadVoiceStatus() {
          try {
            const s = await api('/api/ai/voice_status');
            voiceStatusText.value = `Demucs:${s.demucs?'✓':'×'} Edge-TTS:${s.edge_tts?'✓':'×'} DeepTranslator:${s.deep_translator?'✓':'×'}`;
          } catch (_) {}
        }
        async function toggleRealtime() {
          if (rtRecording.value) {
            rtRecording.value = false;
            try { if (_rtRecorder && _rtRecorder.state !== 'inactive') _rtRecorder.stop(); } catch(_){}
            try { if (_rtMedia) _rtMedia.getTracks().forEach(t => t.stop()); } catch(_){}
            if (_rtTimer) { clearInterval(_rtTimer); _rtTimer = null; }
            rtLog.value += '\n[已停止]\n';
            logAction('停止准实时转写');
            return;
          }
          try {
            _rtMedia = await navigator.mediaDevices.getUserMedia({ audio: true });
            const chunks = [];
            _rtRecorder = new MediaRecorder(_rtMedia);
            _rtRecorder.ondataavailable = (ev) => { if (ev.data && ev.data.size > 0) chunks.push(ev.data); };
            _rtRecorder.onstop = async () => {
              if (!chunks.length) return;
              const blob = new Blob(chunks, { type: 'audio/webm' });
              chunks.length = 0;
              const fd = new FormData();
              fd.append('file', blob, 'chunk.webm');
              try {
                const q = new URLSearchParams({ lang: 'auto', translate: rtTranslate.value ? 'true' : 'false', target_lang: rtTargetLang.value });
                const resp = await fetch('/api/ai/realtime?' + q.toString(), { method: 'POST', body: fd });
                const data = await resp.json();
                if (!resp.ok) throw new Error(data.detail || '失败');
                if (data.text) rtLog.value += data.text + '\n';
                if (data.translated) rtLog.value += '→ ' + data.translated + '\n';
              } catch (e) {
                rtLog.value += '[错误] ' + (e.message || e) + '\n';
              }
              if (rtRecording.value && _rtRecorder) {
                try { _rtRecorder.start(); setTimeout(() => { try { if (_rtRecorder.state === 'recording') _rtRecorder.stop(); } catch(_){} }, 4000); } catch(_){}
              }
            };
            rtRecording.value = true;
            rtLog.value = '[开始]\n';
            logAction('开始准实时转写');
            _rtRecorder.start();
            setTimeout(() => { try { if (_rtRecorder.state === 'recording') _rtRecorder.stop(); } catch(_){} }, 4000);
          } catch (e) {
            ElementPlus.ElMessage.error('无法访问麦克风: ' + (e.message || e));
          }
        }

        async function aiTranscribe(row) {
          try {
            const r = await api('/api/ai/transcribe', {
              method: 'POST',
              body: JSON.stringify({
                path: row.path,
                lang: settings.value.local_ai_lang || 'auto',
              }),
            });
            ElementPlus.ElMessage.success(r.message || '已开始转写');
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          }
        }
        async function aiTranslateSrt(row) {
          try {
            const r = await api('/api/ai/translate_srt', {
              method: 'POST',
              body: JSON.stringify({
                path: row.path,
                provider: settings.value.subtitle_translate_provider || 'deepl',
                target_lang: settings.value.subtitle_target_lang || 'zh',
                source_lang: settings.value.local_ai_lang || '',
              }),
            });
            ElementPlus.ElMessage.success(r.message || '已开始机翻');
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          }
        }
        function playFile(row) {
          const e = (row.ext || '').toLowerCase();
          playerUrl.value = '/api/files/stream?path=' + encodeURIComponent(row.path);
          playerName.value = row.name || '';
          playerIsVideo.value = ['.mp4', '.webm', '.mkv', '.mov'].includes(e);
          playerIsAudio.value = ['.mp3', '.m4a', '.flac', '.wav', '.aac', '.ogg'].includes(e);
          // 换一份媒体就退出上一份的校对台，避免拿着旧行编辑却以为在改新文件
          srtEdit.on = false;
          srtEdit.dirty = false;
          srtEdit.sel = -1;
          revealCard('card-file-player');
          loadTranscript(row.path);
        }
        const VIDEO_EXTS = ['.mp4', '.webm', '.mkv', '.mov'];
        const AUDIO_EXTS = ['.mp3', '.m4a', '.flac', '.wav', '.aac', '.ogg'];
        async function loadTranscript(path) {
          transcript.value = { srt: '', cues: [], message: '' };
          mediaCueIdx.value = -1;
          transcriptPath.value = path || '';
          try {
            const r = await api('/api/ai/transcript?path=' + encodeURIComponent(path));
            const cues = r.cues || [];
            transcript.value = { srt: r.srt || '', cues, message: cues.length ? '' : (r.message || '') };
          } catch (e) {
            // 没字幕也要能正常播放，不把报错甩在播放器上
          }
        }
        function fmtClock(sec) {
          sec = Math.max(0, Math.floor(sec || 0));
          const p = (n) => String(n).padStart(2, '0');
          const h = Math.floor(sec / 3600), m = Math.floor(sec / 60) % 60, s = sec % 60;
          return h ? `${p(h)}:${p(m)}:${p(s)}` : `${p(m)}:${p(s)}`;
        }
        function speakerTagType(sp) {
          const palette = ['primary', 'success', 'warning', 'danger', 'info'];
          return palette[((parseInt(sp, 10) || 1) - 1) % palette.length];
        }
        function seekToCue(c) {
          const el = mediaEl.value;
          if (!el) return;
          el.currentTime = c.start || 0;
          const i = transcript.value.cues.indexOf(c);
          if (i >= 0) mediaCueIdx.value = i;
          if (el.paused) el.play().catch(() => {});
        }
        function onMediaTimeUpdate(ev) {
          const cues = transcript.value.cues;
          if (!cues.length) return;
          const t = ev.target.currentTime || 0;
          let idx = -1;
          for (let i = 0; i < cues.length; i++) {
            if (t >= cues[i].start && t < (cues[i].end || cues[i].start + 5)) { idx = i; break; }
          }
          if (idx === mediaCueIdx.value) return;
          mediaCueIdx.value = idx;
          if (idx < 0) return;
          nextTick(() => {
            const box = transcriptBox.value;
            const el = box && box.querySelector(`[data-ti="${idx}"]`);
            if (!el) return;
            const r1 = el.getBoundingClientRect(), r2 = box.getBoundingClientRect();
            if (r1.top < r2.top || r1.bottom > r2.bottom) {
              box.scrollTop += (r1.top - r2.top) - r2.height / 2 + r1.height / 2;
            }
          });
        }
        async function openSrtEditor() {
          if (!transcriptPath.value) {
            ElementPlus.ElMessage.warning('先在文件列表里播放这一项，再打开逐句校对');
            return false;
          }
          srtEdit.busy = true;
          try {
            const r = await api('/api/ai/srt?path=' + encodeURIComponent(transcriptPath.value));
            srtEdit.rows = (r.cues || []).map((c, i) => ({
              _k: i + 1, start: c.start, end: c.end, speaker: c.speaker || '', text: c.text || '',
            }));
            srtEdit.srt = r.srt || '';
            srtEdit.format = r.format || 'srt';
            srtEdit.mtimeTs = r.mtime_ts || 0;
            srtEdit.sel = -1;
            srtEdit.dirty = false;
            srtQcReset();
            srtEdit.on = true;
            if (!srtEdit.rows.length) ElementPlus.ElMessage.info(r.message || '这份字幕里没有解析出有效句子');
            return true;
          } catch (e) {
            ElementPlus.ElMessage.error(e.message);
            return false;
          } finally {
            srtEdit.busy = false;
          }
        }
        function srtCloseEdit() {
          if (srtEdit.dirty) {
            ElementPlus.ElMessage.warning('还有未保存的改动：先按「保存」写回字幕，或按「放弃修改」退回原样');
            return;
          }
          srtEdit.on = false;
          srtEdit.sel = -1;
          srtQcReset();
        }
        function srtQcReset() {
          srtQc.rows = [];
          srtQc.message = '';
          srtQc.hint = '';
          srtQc.paired = false;
          srtQc.counter = '';
          srtQc.lang = '';
          srtQc.total = 0;
          srtQc.reflect_on = false;
        }
        async function runSrtQc() {
          if (!srtEdit.srt) {
            ElementPlus.ElMessage.warning('先按「逐句校对」打开一份字幕，质检才知道查哪一条');
            return;
          }
          srtQc.busy = true;
          try {
            const r = await api('/api/subtitle/qc', { method: 'POST', body: JSON.stringify({ path: srtEdit.srt }) });
            srtQc.rows = r.rows || [];
            srtQc.paired = !!r.paired;
            srtQc.counter = r.counter || '';
            srtQc.lang = r.lang || '';
            srtQc.total = r.total || 0;
            srtQc.wrap = r.wrap || { width: 16, lines: 3 };
            srtQc.reflect_on = !!r.reflect_on;
            srtQc.hint = r.hint || '';
            srtQc.message = r.message || '';
            if (!srtQc.rows.length) ElementPlus.ElMessage.success(r.message || '没有发现可疑句');
          } catch (e) {
            ElementPlus.ElMessage.error(e.message);
          } finally {
            srtQc.busy = false;
          }
        }
        function qcJumpTo(q) {
          const i = (q.i || 1) - 1;
          if (i < 0 || i >= srtEdit.rows.length) return;
          srtEdit.sel = i;
          nextTick(() => {
            const box = srtEditBox.value;
            const el = box && box.querySelector(`[data-si="${i}"]`);
            if (!el) return;
            box.scrollTop += el.getBoundingClientRect().top - box.getBoundingClientRect().top
              - box.clientHeight / 2 + el.clientHeight / 2;
          });
          const m = mediaEl.value;
          if (m) {
            m.currentTime = q.start || 0;
            if (m.paused) m.play().catch(() => {});
          }
        }
        async function runSrtRewrap() {
          if (!srtEdit.srt) {
            ElementPlus.ElMessage.warning('先按「逐句校对」打开一份字幕，重排才知道改哪一条');
            return;
          }
          if (srtEdit.dirty) {
            ElementPlus.ElMessage.warning('重排改的是磁盘上的字幕：请先按「保存」写回行内改动，或按「放弃修改」退回磁盘版本');
            return;
          }
          srtQc.busy = true;
          try {
            const r = await api('/api/subtitle/rewrap', { method: 'POST', body: JSON.stringify({ path: srtEdit.srt }) });
            ElementPlus.ElMessage.success(r.message || '已按每行字数重排');
            await openSrtEditor();
            srtQc.message = r.message || '';
          } catch (e) {
            ElementPlus.ElMessage.error(e.message);
          } finally {
            srtQc.busy = false;
          }
        }
        async function srtDiscard() {
          if (await openSrtEditor()) {
            ElementPlus.ElMessage.info('已放弃未保存的改动，重新读回了磁盘上的字幕');
          }
        }
        function srtShiftSel(step) {
          const r = srtEdit.rows[srtEdit.sel];
          if (!r) return;
          const dur = Math.max(0.04, (r.end || 0) - (r.start || 0));
          r.start = Math.max(0, +(((r.start || 0) + step).toFixed(3)));
          r.end = +(r.start + dur).toFixed(3);
          srtEdit.dirty = true;
        }
        function srtMerge(i) {
          const a = srtEdit.rows[i], b = srtEdit.rows[i + 1];
          if (!a || !b) return;
          a.text = (String(a.text || '') + ' ' + String(b.text || '')).trim();
          if ((b.end || 0) > (a.end || 0)) a.end = b.end;
          if (!a.speaker && b.speaker) a.speaker = b.speaker;
          srtEdit.rows.splice(i + 1, 1);
          if (srtEdit.sel >= srtEdit.rows.length) srtEdit.sel = srtEdit.rows.length - 1;
          srtEdit.dirty = true;
        }
        function srtDrop(i) {
          srtEdit.rows.splice(i, 1);
          if (srtEdit.sel >= srtEdit.rows.length) srtEdit.sel = srtEdit.rows.length - 1;
          srtEdit.dirty = true;
        }
        async function srtSave() {
          if (!srtEdit.rows.length) {
            ElementPlus.ElMessage.warning('句子已经全部删空，这样保存等于把整份字幕清空。要退回原样请按「放弃修改」');
            return;
          }
          srtEdit.busy = true;
          try {
            const r = await api('/api/ai/srt/save', {
              method: 'POST',
              uiName: '保存逐句字幕校对',
              body: JSON.stringify({
                path: transcriptPath.value,
                base_mtime: srtEdit.mtimeTs,
                cues: srtEdit.rows.map(c => ({ start: c.start, end: c.end, speaker: c.speaker, text: c.text })),
              }),
            });
            srtEdit.mtimeTs = r.mtime_ts || 0;
            srtEdit.dirty = false;
            ElementPlus.ElMessage.success(r.message + '，改前的内容备份为 ' + String(r.backup || '').split('/').pop());
            await loadTranscript(transcriptPath.value);
          } catch (e) {
            ElementPlus.ElMessage.error(e.message);
          } finally {
            srtEdit.busy = false;
          }
        }
        function zipPath(path, name) {
          logAction(actionName('/api/files/zip'));
          const a = document.createElement('a');
          a.href = '/api/files/zip';
          // 使用 fetch POST 下载 blob
          fetch('/api/files/zip', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: path || '', name: name || 'archive' })
          }).then(async (res) => {
            if (!res.ok) throw new Error(await res.text());
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = (name || 'archive') + '.zip';
            link.click();
            URL.revokeObjectURL(url);
          }).catch(e => ElementPlus.ElMessage.error(e.message || '打包失败'));
        }
        function zipCurrentFolder() {
          zipPath(filesPath.value || '', filesPath.value ? filesPath.value.split('/').pop() : 'downloads');
        }

        
        async function loadPlatformCookies() {
          try {
            const data = await api('/api/platforms/cookies');
            platformCookies.value = (data.platforms || []).map(p => ({ ...p, _text: '' }));
          } catch (_) {}
        }
        async function savePlatformCookie(p) {
          try {
            await api('/api/platforms/cookies', {
              method: 'POST',
              body: JSON.stringify({ platform: p.platform, source: p.source, file: p.file, browser: p.browser }),
            });
            ElementPlus.ElMessage.success(p.label + ' Cookie 已保存');
            await loadPlatformCookies();
          } catch (e) {
            ElementPlus.ElMessage.error(e.message);
          }
        }
        async function savePlatformCookieText(p) {
          if (!(p._text || '').trim()) {
            ElementPlus.ElMessage.warning('请先粘贴 Cookie 文本');
            return;
          }
          try {
            await api('/api/platforms/cookies/save-text', {
              method: 'POST',
              body: JSON.stringify({ platform: p.platform, content: p._text }),
            });
            ElementPlus.ElMessage.success('已写入 ' + p.label + ' Cookie 文件');
            p._text = '';
            await loadPlatformCookies();
          } catch (e) {
            ElementPlus.ElMessage.error(e.message);
          }
        }
        async function clearCookieFlag(p) {
          try {
            await api('/api/platforms/cookies/clear-flag', {
              method: 'POST',
              body: JSON.stringify({ platform: p.platform }),
            });
            ElementPlus.ElMessage.success('已清除 ' + p.label
              + ' 的登录态标记（这个平台再有下载被判定为需要登录时会重新标出）');
            await loadPlatformCookies();
          } catch (e) {
            ElementPlus.ElMessage.error(e.message);
          }
        }
        async function browsePlatformCookie(p) {
          try {
            const data = await api('/api/browse', { method: 'POST', body: JSON.stringify({ mode: 'file', title: '选择 Cookie 文件' }) });
            if (data.path) p.file = data.path;
          } catch (e) {
            ElementPlus.ElMessage.error(e.message);
          }
        }
        async function loadMusicCookies() {
          try {
            const data = await api('/api/music/cookies');
            musicCookieItems.value = data.items || [];
          } catch (_) {}
        }
        async function saveMusicCookie(p) {
          const text = (musicCookieText.value[p.platform] || '').trim();
          if (!text) {
            ElementPlus.ElMessage.warning('请先粘贴 Cookie 内容');
            return;
          }
          try {
            const r = await api('/api/music/cookies', { method: 'POST', body: JSON.stringify({ platform: p.platform, cookie: text }) });
            musicCookieItems.value = r.items || [];
            musicCookieText.value[p.platform] = '';
            ElementPlus.ElMessage[r.missing && r.missing.length ? 'warning' : 'success'](
              r.missing && r.missing.length
                ? `${p.label} Cookie 已保存，但缺 ${r.missing.join(' 或 ')}，这个源仍拿不到会员音质`
                : `${p.label} Cookie 已保存`);
          } catch (e) {
            ElementPlus.ElMessage.error(e.message);
          }
        }
        async function clearMusicCookie(p) {
          try {
            const r = await api('/api/music/cookies', { method: 'POST', body: JSON.stringify({ platform: p.platform, cookie: '' }) });
            musicCookieItems.value = r.items || [];
            ElementPlus.ElMessage.info(`${p.label} Cookie 已清除`);
          } catch (e) {
            ElementPlus.ElMessage.error(e.message);
          }
        }
        function applyNcQrResult(pr) {
          ncQrMsg.value = pr.message || '';
          if (pr.ok) {
            if (pr.items) musicCookieItems.value = pr.items;
            ElementPlus.ElMessage.success('网易云音乐登录成功，Cookie 已保存');
          }
          if (pr.ok || pr.status === 'expired') {
            ncQrKey.value = ''; ncQrImage.value = ''; ncQrUrl.value = '';
          }
          return pr.ok || pr.status === 'expired';
        }
        async function startNeteaseQr() {
          ncQrLoading.value = true;
          ncQrMsg.value = '';
          ncQrImage.value = '';
          try {
            const r = await api('/api/music/netease/qr/generate');
            ncQrUrl.value = r.url || '';
            ncQrKey.value = r.qrcode_key || '';
            ncQrImage.value = r.qr_image || '';
            ncQrMsg.value = '扫码后在手机上点确认，页面会自动检测登录结果';
            if (!ncQrKey.value) return;
            let n = 0;
            const timer = setInterval(async () => {
              n += 1;
              try {
                const pr = await api('/api/music/netease/qr/poll', { method: 'POST', noLog: true, body: JSON.stringify({ qrcode_key: ncQrKey.value }) });
                if (applyNcQrResult(pr) || n >= 100) clearInterval(timer);
              } catch (_) {
                if (n >= 100) clearInterval(timer);
              }
            }, 3000);
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '获取二维码失败');
          } finally {
            ncQrLoading.value = false;
          }
        }
        async function pollNeteaseQr() {
          if (!ncQrKey.value) return;
          try {
            applyNcQrResult(await api('/api/music/netease/qr/poll', { method: 'POST', body: JSON.stringify({ qrcode_key: ncQrKey.value }) }));
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '检查失败');
          }
        }
        function canonMusicSource(s) {
          const v = String(s || '').trim();
          if (!v) return '';
          if (/client$/i.test(v)) return v;
          const low = v.toLowerCase() + 'musicclient';
          const hit = (musicSourceOptions.value || []).find((o) => o.toLowerCase() === low);
          return hit || (v.charAt(0).toUpperCase() + v.slice(1) + 'MusicClient');
        }
        async function ensureMusicStatus() {
          const st = await api('/api/music/status');
          musicdlVersion.value = st.musicdl_version || '';
          musicdlReady.value = !!st.musicdl;
          if (st.ui_sources && st.ui_sources.length) {
            musicSourceOptions.value = [...new Set(st.ui_sources)];
          }
          if (st.saved_sources && st.saved_sources.length && !window.__musicSourcesRestored) {
            musicSources.value = [...new Set(st.saved_sources.map(canonMusicSource).filter(Boolean))];
            window.__musicSourcesRestored = true;
          }
          musicSources.value = [...new Set(musicSources.value.map(canonMusicSource).filter(Boolean))];
          musicSourceOptions.value = [...new Set(musicSourceOptions.value)];
          if (st.presets) window.__musicPresets = st.presets;
          if (st.source_hints) window.__musicSourceHints = st.source_hints;
          syncMusicPreset();
          if (st.strategy && typeof st.strategy === 'object') {
            musicStrategy.value = Object.assign({}, musicStrategy.value, st.strategy);
          }
          if (st.quality_options) {
            const qo = st.quality_options;
            const khz = (v) => (v / 1000).toFixed(1).replace(/\.0$/, '');
            musicQualityOptions.value = {
              format: (qo.format || []).map((x) => ({ value: x[0], label: x[1] })),
              bit_depth: (qo.bit_depth || []).map((v) => ({ value: v, label: v ? v + 'bit 以上' : '位深不限' })),
              sample_rate: (qo.sample_rate || []).map((v) => ({ value: v, label: v ? khz(v) + 'kHz 以上' : '采样率不限' })),
              bitrate: (qo.bitrate || []).map((v) => ({ value: v, label: v ? v + 'k 以上' : '码率不限' })),
            };
          }
          if (st.quality_spec && typeof st.quality_spec === 'object') {
            musicQualitySpec.value = Object.assign({}, musicQualitySpec.value, st.quality_spec);
          }
          if (!window.__playlistModeRestored && (st.playlist_mode === 'fast' || st.playlist_mode === 'quality')) {
            musicPlaylistMode.value = st.playlist_mode;
            window.__playlistModeRestored = true;
          }
          if (!window.__blockReuploadRestored && typeof st.block_reupload === 'boolean') {
            musicBlockReupload.value = st.block_reupload;
            window.__blockReuploadRestored = true;
          }
          if (!window.__includeRefRestored && typeof st.include_reference === 'boolean') {
            musicIncludeReference.value = st.include_reference;
            window.__includeRefRestored = true;
          }
          // 模板与三个勾选后端一直在用，重开页面不回填就会显示默认值，再点一次「保存策略」把存好的冲掉
          if (!window.__musicPrefsRestored) {
            if (st.filename_template) musicFilenameTemplate.value = st.filename_template;
            if (typeof st.embed_metadata === 'boolean') musicEmbedMeta.value = st.embed_metadata;
            if (typeof st.hide_unavailable === 'boolean') musicHideUnavailable.value = st.hide_unavailable;
            if (typeof st.include_local === 'boolean') musicIncludeLocal.value = st.include_local;
            window.__musicPrefsRestored = true;
          }
          return st;
        }
        function musicKeywordLines() {
          return String(musicKeyword.value || '')
            .split(/[\n;；]+/)
            .map(s => s.trim())
            .filter(Boolean);
        }
        async function searchOneMusicKeyword(q) {
          const r = await api('/api/music/search', {
            method: 'POST',
            body: JSON.stringify({
              keyword: q,
              limit: musicStrategy.value.search_size || 12,
              sources: musicSources.value,
              cookies: musicCookies.value || '',
              strategy: musicStrategy.value,
              search_type: musicSearchType.value || 'song',
              include_local: !!musicIncludeLocal.value,
              hide_unavailable: musicHideUnavailable.value !== false,
              include_reference: !!musicIncludeReference.value,
            }),
          });
          return r;
        }
        async function searchMusic() {
          const lines = musicKeywordLines();
          if (!lines.length) {
            ElementPlus.ElMessage.warning('请输入关键词（支持多行批量）');
            return;
          }
          musicSearching.value = true;
          musicSourceErrors.value = [];
          try {
            await ensureMusicStatus();
            const merged = [];
            const seen = new Set();
            let statsAll = {};
            const errsAll = {};
            let elapsedAll = 0;
            for (const q of lines) {
              const r = await searchOneMusicKeyword(q);
              for (const it of (r.items || [])) {
                const key = (it.id || '') + '|' + (it.title || '') + '|' + (it.artists || '') + '|' + (it.source || '');
                if (seen.has(key)) continue;
                seen.add(key);
                merged.push(it);
              }
              if (r.source_stats) {
                for (const [k, v] of Object.entries(r.source_stats)) {
                  statsAll[k] = (statsAll[k] || 0) + (v || 0);
                }
              }
              elapsedAll += (r.elapsed || 0);
              for (const [k, v] of Object.entries(r.source_errors || {})) {
                errsAll[(lines.length > 1 ? q + ' · ' : '') + k] = v;
              }
            }
            musicSourceErrors.value = Object.entries(errsAll);
            musicResults.value = merged;
            let msg = lines.length > 1
              ? `批量 ${lines.length} 词 → ${merged.length} 条`
              : `找到 ${merged.length} 条`;
            if (Object.keys(statsAll).length) {
              msg += '（' + Object.entries(statsAll).map(([k,v]) => k + ':' + v).join(', ') + '）';
            }
            if (elapsedAll) msg += ` · ${elapsedAll.toFixed(0)}s`;
            if (musicSourceErrors.value.length) {
              ElementPlus.ElMessage.warning({
                message: msg + `｜${musicSourceErrors.value.length} 个源无结果，原因见结果上方`,
                duration: 6000,
              });
            } else {
              ElementPlus.ElMessage.success(msg);
            }
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          } finally {
            musicSearching.value = false;
          }
        }
        async function batchSearchDownload() {
          const lines = musicKeywordLines();
          if (!lines.length) {
            ElementPlus.ElMessage.warning('每行一条：歌名 或 歌名 - 歌手');
            return;
          }
          musicSearching.value = true;
          try {
            await ensureMusicStatus();
            const toDownload = [];
            const merged = [];
            const seen = new Set();
            for (const q of lines) {
              const r = await searchOneMusicKeyword(q);
              const items = r.items || [];
              for (const it of items) {
                const key = (it.id || '') + '|' + (it.title || '') + '|' + (it.source || '');
                if (seen.has(key)) continue;
                seen.add(key);
                merged.push(it);
              }
              // 每条关键词取第一条可用结果
              const hit = items.find(x => x.id || x.url) || items[0];
              if (hit) toDownload.push(hit);
            }
            musicResults.value = merged;
            if (!toDownload.length) {
              ElementPlus.ElMessage.warning('没有可下载结果');
              return;
            }
            musicSelected.value = toDownload.map(x => x.id || x.url).filter(Boolean);
            await downloadMusicSelected();
            ElementPlus.ElMessage.success(`已按 ${toDownload.length}/${lines.length} 条关键词加入下载`);
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          } finally {
            musicSearching.value = false;
          }
        }
        // 这一行能不能播：参照行不是成品，待匹配行还没有地址
        function playableOf(r) {
          if (!r || r.reference_only || r.needs_match) return null;
          const url = (r.is_local && r.path)
            ? '/api/files/stream?path=' + encodeURIComponent(r.path)
            : (r.id || r.slot)
              ? '/api/music/preview?id=' + encodeURIComponent(r.id || r.slot)
              : (r.url && String(r.url).startsWith('http'))
                ? '/api/music/preview?url=' + encodeURIComponent(r.url) : '';
          if (!url) return null;
          return { url, title: r.title || '（未知曲名）', sub: r.artists || '',
                   cover: (r.is_local && r.cover_url) ? r.cover_url : '', row: r };
        }
        // 高精度 LRC：结果自带文本 > 音频内嵌歌词 > 同名歌词文件
        async function fetchRowLyrics(row) {
          try {
            if (row.lyrics || row.lyric) {
              const r = await api('/api/music/lyrics', { method: 'POST', body: JSON.stringify({ text: row.lyrics || row.lyric }) });
              return r.lines || [];
            }
            const candidates = [];
            if (row.is_local && row.has_lyrics && row.path) candidates.push(row.path);
            if (row.is_local && row.lyrics_path) candidates.push(row.lyrics_path);
            for (const c of candidates) {
              try {
                const r = await api('/api/music/lyrics', { method: 'POST', body: JSON.stringify({ path: c }) });
                if (r.lines && r.lines.length) return r.lines;
              } catch (_) {}
            }
          } catch (_) {}
          return [];
        }
        async function playerLoad(track) {
          player.url = track.url;
          player.title = track.title;
          player.sub = track.sub;
          player.cover = track.cover;
          playerTime.value = 0;
          playerDur.value = 0;
          playerSeeking.value = false;
          musicLrcLines.value = [];
          musicLrcActive.value = -1;
          await nextTick();
          const el = playerEl.value;
          if (el) {
            el.volume = playerVol.value;
            el.muted = playerMuted.value || playerVol.value <= 0;
            el.load();
            el.play().catch(() => {});   // 浏览器拦下自动播放时，播放条还在，点一下即可
          }
          const lines = await fetchRowLyrics(track.row);
          if (player.queue[player.idx] === track) musicLrcLines.value = lines;
        }
        // 队列 = 用户点开的那一份清单里能播的行，上一首/下一首就沿着它走
        async function playFrom(list, row, from) {
          const pool = (list || []).map(playableOf).filter(Boolean);
          let i = pool.findIndex(x => x.row === row);
          if (i < 0) {
            const one = playableOf(row);
            if (!one) { ElementPlus.ElMessage.warning('这一行没有可试听的音频地址'); return; }
            pool.unshift(one);
            i = 0;
          }
          player.queue = pool;
          player.idx = i;
          player.from = from || 'search';
          await playerLoad(pool[i]);
        }
        function previewMusicRow(row, list) {
          return playFrom(list || musicResults.value, row, 'search');
        }
        function playerStep(d) {
          const i = player.idx + d;
          if (i < 0 || i >= player.queue.length) return;
          player.idx = i;
          playerLoad(player.queue[i]);
        }
        function playerToggle() {
          const el = playerEl.value;
          if (!el || !player.url) return;
          if (el.paused) el.play().catch(() => {}); else el.pause();
        }
        function playerClose() {
          const el = playerEl.value;
          if (el) { el.pause(); el.removeAttribute('src'); el.load(); }
          player.url = ''; player.title = ''; player.sub = ''; player.cover = '';
          player.queue = []; player.idx = -1; player.from = '';
          playerTime.value = 0; playerDur.value = 0;
          musicLrcLines.value = []; musicLrcActive.value = -1;
        }
        function onPlayerMeta(ev) {
          const d = Number(ev.target.duration) || 0;
          if (d > 0 && isFinite(d)) playerDur.value = d;
        }
        function onPlayerTick(ev) {
          const t = Number(ev.target.currentTime) || 0;
          if (!playerSeeking.value) playerTime.value = t;
          const lines = musicLrcLines.value || [];
          let idx = -1;
          for (let i = 0; i < lines.length; i++) {
            if (t >= (lines[i].start || 0) && t < (lines[i].end || lines[i].start + 5)) idx = i;
          }
          musicLrcActive.value = idx;
        }
        function onPlayerEnded() {
          if (player.idx + 1 < player.queue.length) playerStep(1); else playerPlaying.value = false;
        }
        function playerSeek(ev) {
          const t = Number(ev.target.value) || 0;
          playerSeeking.value = true;
          playerSeekVal.value = t;
          playerTime.value = t;
          const el = playerEl.value;
          if (el) el.currentTime = t;
        }
        // 焦点在输入框 / 按钮上，或弹窗开着的时候不抢空格：那是用户在打字或按按钮
        function onSpaceKey(ev) {
          if (ev.code !== 'Space' || ev.altKey || ev.ctrlKey || ev.metaKey || ev.shiftKey) return;
          if (!player.url) return;
          const t = ev.target;
          if (!t || t.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName)) return;
          if (t.closest && t.closest('button, a, [role="button"], .el-overlay, .el-popper')) return;
          ev.preventDefault();
          playerToggle();
        }
        watch(playerVol, (v) => {
          const el = playerEl.value;
          if (el) { el.volume = v; el.muted = playerMuted.value || v <= 0; }
        });
        watch(playerMuted, (m) => {
          const el = playerEl.value;
          if (el) el.muted = m || playerVol.value <= 0;
        });
        async function probeMusicRow(row) {
          const url = row.url || '';
          if (!url.startsWith('http')) { ElementPlus.ElMessage.info('无直接链接可探测'); return; }
          try {
            const r = await api('/api/music/probe', { method: 'POST', body: JSON.stringify({ url }) });
            const mb = r.size ? (r.size/1048576).toFixed(2) + ' MB' : '未知';
            ElementPlus.ElMessage.success(`大小 ${mb}` + (r.accept_ranges ? ' · 支持 Range' : ''));
          } catch (e) { ElementPlus.ElMessage.error(String(e.message || e)); }
        }
        // 换源：让后端到「匹配源」里的其他平台重新找这一首，只有判定确实是同一首歌才改写清单。
        async function switchMusicSource(rows) {
          const list = (rows || []).filter(r => r && r.id && !r.reference_only && !r.is_local);
          if (!list.length) {
            ElementPlus.ElMessage.warning('这些行换不了源：本地音乐和无损参照都没有「换一条来路」这回事');
            return;
          }
          musicSwitching.value = musicSwitching.value.concat(list.map(r => r.id));
          try {
            const r = await api('/api/music/switch_source', {
              method: 'POST',
              body: JSON.stringify({
                ids: list.map(x => x.id),
                sources: (musicStrategy.value && musicStrategy.value.match_sources) || [],
                cookies: musicCookies.value || '',
              }),
            });
            const byId = {};
            (r.results || []).forEach(x => { byId[x.id] = x; });
            const fails = [];
            list.forEach(row => {
              const x = byId[row.id] || {};
              row.switch_fail = '';
              if (!x.ok) {
                row.switch_fail = x.reason || '后端没回这一行的结论';
                fails.push(`「${row.title || '（未知曲名）'}」—— ${row.switch_fail}`);
                return;
              }
              const n = x.row || {};
              Object.assign(row, {
                title: n.title || row.title,
                artists: n.artists || row.artists,
                album: n.album != null ? n.album : row.album,
                duration: n.duration || row.duration,
                duration_s: n.duration_s || row.duration_s,
                url: n.url || row.url,
                cover: n.cover || row.cover,
                quality: n.quality || row.quality,
                source: n.source || row.source,
                musicdl_source: n.musicdl_source || row.musicdl_source,
                real_source: n.real_source || '',
                unofficial: !!n.unofficial,
                needs_match: false,
                reupload_suspect: false,
                // 换源把这一行换成另一条结果了：那个「与关键词的吻合度」是老的行算出来的，
                // 留着不换就等于挂着一条对不上号的分数。同曲判定另在 switch_note 里写。
                score: null, score_name: null, score_artist: null, score_time: null, score_reject: '',
                switch_note: `从 ${x.from || '原平台'} 换成 ${x.to}（同曲判定 ${x.score} 分）`,
              });
            });
            const okN = list.length - fails.length;
            const txt = `换源结束：${okN} 首已换成别的平台`
              + (fails.length ? `，${fails.length} 首没换成，清单保持原样` : '')
              + '（逐首结论见运行日志）';
            if (okN && fails.length) ElementPlus.ElMessage.warning(txt);
            else if (okN) ElementPlus.ElMessage.success(txt);
            else ElementPlus.ElMessage.warning(fails.length ? txt : '换源结束：没有结果');
            if (fails.length) {
              const esc = (t) => String(t).replace(/[&<>"']/g, (c) => (
                { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
              ElementPlus.ElMessageBox.alert(
                '<div class="unmatched-h">这些行没换成（判定不是同一首歌，或别的平台压根没这首）：</div>'
                + `<div class="unmatched-l">${fails.map(esc).join('<br>')}</div>`,
                '换源未成功的曲目',
                { dangerouslyUseHTMLString: true, confirmButtonText: '知道了', customClass: 'unmatched-box' },
              ).catch(() => {});
            }
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          } finally {
            const done = new Set(list.map(r => r.id));
            musicSwitching.value = musicSwitching.value.filter(i => !done.has(i));
          }
        }
        function refHint(row) {
          const bits = [row.bit_depth ? row.bit_depth + 'bit' : '',
                        row.sampling_rate ? row.sampling_rate + 'kHz' : ''].filter(Boolean).join('/');
          const parts = [row.real_source || '官方曲库元数据'];
          if (row.isrc) parts.push('ISRC ' + row.isrc);
          if (bits) parts.push(bits);
          if (row.duration) parts.push('时长 ' + row.duration);
          if (row.version) parts.push('版本标注「' + row.version + '」');
          if (row.date) parts.push('发行 ' + row.date);
          if (row.label) parts.push('厂牌 ' + row.label);
          parts.push('只读，音频不从这一行下');
          return parts.join(' · ');
        }
        function matchHint(row) {
          const line = row.match_accept || 85;
          const f = (v) => (v === null || v === undefined) ? '未参与' : String(Math.round(v));
          const parts = [`这一条与你输入的关键词的吻合度：${row.score} / 100（录取线 ${line}）`];
          parts.push(`曲名 ${f(row.score_name)} · 歌手 ${f(row.score_artist)} · 时长 ${f(row.score_time)}`);
          if (row.score_reject) parts.push('挡下来的原因：' + row.score_reject);
          parts.push('这一分管的是「对不对得上你输入的关键词」。要判「与某条标注是不是同一版录音」得有时长可比，'
                     + '换源与查重走的是那一套管');
          parts.push('阈值写死在后端 music_search 的 MATCH_* 里，目前不能在界面改');
          return parts.join('\n');
        }
        function openRefLink(row) {
          const url = String(row.url || '');
          if (!url.startsWith('http')) { ElementPlus.ElMessage.info('这一行没有官方页面链接'); return; }
          window.open(url, '_blank', 'noopener');
        }
        async function scanLocalMusic() {
          try {
            const r = await api('/api/music/local_scan', { method: 'POST', body: JSON.stringify({}) });
            ElementPlus.ElMessage.success(`本地索引 ${r.count || 0} 首，索引文件在 ${r.index_file || '（未返回）'}`);
          } catch (e) { ElementPlus.ElMessage.error(String(e.message || e)); }
        }
        // 界面上这一份就是本次要交给后端的：不发给下载接口的话，后端只会读上次保存的值，
        // 改了没点保存就下载会静默按旧要求跑
        function musicQualityBody() {
          const s = musicQualitySpec.value || {};
          return {
            format: s.format || '',
            min_bit_depth: Number(s.min_bit_depth) || 0,
            min_sample_rate: Number(s.min_sample_rate) || 0,
            min_bitrate: Number(s.min_bitrate) || 0,
            strict: !!s.strict,
          };
        }
        async function saveMusicStrategy() {
          try {
            // 合并进全局配置
            settings.value.musicdl_strategy = Object.assign({}, musicStrategy.value);
            await api('/api/config', {
              method: 'POST',
              body: JSON.stringify({
                musicdl_strategy: musicStrategy.value,
                music_filename_template: musicFilenameTemplate.value,
                music_embed_metadata: !!musicEmbedMeta.value,
                music_hide_unavailable: musicHideUnavailable.value !== false,
                music_include_local: !!musicIncludeLocal.value,
                music_block_reupload: !!musicBlockReupload.value,
                music_include_reference: !!musicIncludeReference.value,
                music_quality_spec: {
                  format: musicQualitySpec.value.format || '',
                  min_bit_depth: Number(musicQualitySpec.value.min_bit_depth) || 0,
                  min_sample_rate: Number(musicQualitySpec.value.min_sample_rate) || 0,
                  min_bitrate: Number(musicQualitySpec.value.min_bitrate) || 0,
                  strict: !!musicQualitySpec.value.strict,
                },
              }),
            });
            ElementPlus.ElMessage.success('策略与模板已保存');
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          }
        }
        function applyMusicPreset(v) {
          const presets = musicPresetMap();
          if (!presets[v]) return;
          musicSources.value = presets[v].slice();
        }
        async function saveMusicPlaylistMode() {
          try {
            await api('/api/config', {
              method: 'POST',
              body: JSON.stringify({ music_playlist_mode: musicPlaylistMode.value }),
            });
          } catch (e) {
            ElementPlus.ElMessage.error('保存解析方式失败：' + String(e.message || e));
          }
        }
        async function parseMusicPlaylist() {
          const url = (musicPlaylistUrl.value || '').trim();
          if (!url.startsWith('http')) {
            ElementPlus.ElMessage.warning('请粘贴歌单链接');
            return;
          }
          const quality = musicPlaylistMode.value === 'quality';
          musicSearching.value = true;
          ElementPlus.ElMessage.info({
            message: quality
              ? '高音质模式：musicdl 逐曲取地址，几十首通常要 1-3 分钟，最长等 15 分钟'
              : '正在列出歌单曲目（yt-dlp 优先，通常几秒）；酷狗/咪咕/Spotify 这类只有 musicdl 认，需要逐曲等',
            duration: 8000,
          });
          try {
            const r = await api('/api/music/playlist', {
              method: 'POST',
              body: JSON.stringify({
                url, sources: musicSources.value, cookies: musicCookies.value || '',
                prefer: musicPlaylistMode.value,
              }),
            });
            musicResults.value = r.items || [];
            const hint = (r.diag && r.diag.hint) || '';
            const engine = (r.diag && r.diag.engine) || '';
            if ((r.count || 0) > 0) {
              const note = engine === 'yt-dlp'
                ? '（yt-dlp 列曲目，下载走链接）'
                : (engine === 'spotify-list'
                    ? '（Spotify 只列了曲目，下载时才按曲名去勾选的源里匹配地址）'
                    : '（musicdl 逐曲取址）');
              const dup = (r.diag && r.diag.dup_merged) || 0;
              ElementPlus.ElMessage.success(`歌单 ${r.count} 首${note}`
                + (dup ? `，已合并 ${dup} 首重复（同一首歌排了多遍，下载只下一遍）` : ''));
            } else {
              ElementPlus.ElMessage.error({
                message: `歌单解析失败：${hint || '各源都没返回曲目，详见下方日志'}`,
                duration: 8000,
              });
            }
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          } finally {
            musicSearching.value = false;
          }
        }
        function onMusicSelection(rows) {
          musicSelected.value = rows || [];
        }
        // 批量下载走的是后台线程、不入下载队列，队列页看不见它；只能轮询状态接口等整批结束
        let musicBatchTimer = null;
        function watchMusicBatch(since, favCtx) {
          if (musicBatchTimer) clearInterval(musicBatchTimer);
          let misses = 0;
          musicBatchTimer = setInterval(async () => {
            let s = null;
            try { s = await api('/api/music/download_status'); } catch (e) { s = null; }
            if (!s || (since && s.started_at !== since)) {
              if (++misses > 3) { clearInterval(musicBatchTimer); musicBatchTimer = null; }
              return;
            }
            misses = 0;
            if (!s.finished) return;
            clearInterval(musicBatchTimer);
            musicBatchTimer = null;
            await markMusicFavs(s, favCtx);
            const skip = Math.max(0, (s.total || 0) - (s.ok || 0));
            const dupSkip = s.dup_skipped || 0;
            const have = s.already || 0;
            const miss = (s.match && s.match.missed) || [];
            const lazy = (s.match && s.match.unsearched) || [];
            const hasList = miss.length + lazy.length > 0;
            const txt = `${favCtx ? '收藏清单下载结束' : '多选下载结束'}：成功 ${s.ok || 0} 首`
              + (skip ? `，${skip} 首没取到地址${hasList ? '（清单见下）' : '（原因见运行日志）'}` : '')
              + (dupSkip ? `，${dupSkip} 首是重复排的、只下了一遍` : '')
              + (have ? `，${have} 首目录里已有同名成品、没再下一份` : '')
              + `，用时 ${Math.round(s.elapsed_s || 0)} 秒`;
            if (s.ok) ElementPlus.ElMessage.success(txt);
            else ElementPlus.ElMessage.warning(txt);
            if (hasList) showUnmatched(miss, lazy, (s.match && s.match.sources) || '');
            showAlreadyHave(s.already_list);
            loadFiles().catch(() => {});
          }, 4000);
        }
        const escHtml = (t) => String(t).replace(/[&<>"']/g, (c) => (
          { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
        // 「跳过已下载」到底跳了哪几首、凭什么算同一首：只报数量的话没人知道自己少下了什么
        function showAlreadyHave(list) {
          const rows = (list || []).map(x => `${x.title || '（未知曲名）'} → ${String(x.path || '').split(/[\\/]/).pop()}`
            + `（同一首判定 ${Math.round(x.score || 0)} 分，目录里那首叫「${x.local_title || '（无标签）'}」）`);
          if (!rows.length) return;
          ElementPlus.ElMessageBox.alert(
            `<div class="unmatched-h">下载目录里已经有一版，这次没有下第二份的 ${rows.length} 首</div>`
            + `<div class="unmatched-l">${rows.map(escHtml).join('、')}</div>`
            + `<div class="unmatched-h">判定按曲名 + 歌手 + 时长打分，不看文件名；要重下这一批就取消勾选清单上方的「跳过已下载的歌」</div>`,
            '目录里已经有同一首歌',
            { dangerouslyUseHTMLString: true, confirmButtonText: '知道了', customClass: 'unmatched-box' },
          ).catch(() => {});
        }
        // 匹配那一轮没找到 / 没轮到搜的歌整份列出来：只报前几首会让人以为就少这几首
        function showUnmatched(miss, lazy, srcNames) {
          const block = (head, rows) => rows.length
            ? `<div class="unmatched-h">${escHtml(head)}</div>`
              + `<div class="unmatched-l">${rows.map(escHtml).join('、')}</div>`
            : '';
          ElementPlus.ElMessageBox.alert(
            block(`在 ${srcNames || '勾选的匹配源'} 里按曲名没找到同一首歌，已跳过 ${miss.length} 首`, miss)
            + block(`本轮没轮到搜 ${lazy.length} 首（整轮时间预算用满，不是没找到），再下一次即可`, lazy),
            '按曲名未匹配的曲目',
            { dangerouslyUseHTMLString: true, confirmButtonText: '知道了', customClass: 'unmatched-box' },
          ).catch(() => {});
        }
        async function downloadMusicSelected() {
          const rows = musicSelected.value || [];
          if (!rows.length) return;
          const cacheIds = rows.filter(r => r.id).map(r => r.id);
          const urls = rows.filter(r => r.url && !r.id).map(r => r.url);
          try {
            if (cacheIds.length) {
              const r = await api('/api/music/download', {
                method: 'POST',
                body: JSON.stringify({
                  ids: cacheIds, cookies: musicCookies.value || '',
                  match_sources: musicStrategy.value.match_sources || [],
                  skip_downloaded: musicSkipExisting.value !== false,
                  block_reupload: !!musicBlockReupload.value,
                  quality_spec: musicQualityBody(),
                }),
              });
              ElementPlus.ElMessage.success(r.message || 'musicdl 下载中');
              watchMusicBatch(r.started_at);
            }
            if (urls.length) {
              await api('/api/music/download', {
                method: 'POST',
                body: JSON.stringify({ urls, cookies: musicCookies.value || '' }),
              });
              ElementPlus.ElMessage.success(`已入队 ${urls.length} 首`);
              page.value = 'queue';
              loadTasks();
            }
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          }
        }
        async function downloadMusicRow(row) {
          if (!row) return;
          try {
            const body = {
              ids: row.id ? [row.id] : [],
              urls: row.url && !row.id ? [row.url] : [],
              title: row.title || '',
              artists: row.artists || '',
              source: row.source || '',
              musicdl_source: row.musicdl_source || '',
              can_musicdl_download: !!row.can_musicdl_download,
              cookies: musicCookies.value || '',
              match_sources: musicStrategy.value.match_sources || [],
              // 单首是明确的一次动作：目录里已有也重新下，归档时替换旧那份，不另存副本
              skip_downloaded: false,
              block_reupload: !!musicBlockReupload.value,
              quality_spec: musicQualityBody(),
            };
            const r = await api('/api/music/download', { method: 'POST', body: JSON.stringify(body) });
            ElementPlus.ElMessage.success(
              r.message || (r.mode === 'musicdl' ? 'musicdl 下载中' : `已入队 ${r.count || 1} 首`)
            );
            if (r.mode === 'queue') {
              page.value = 'queue';
              loadTasks();
            }
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          }
        }
        /* ---- 自建收藏清单：跨源攒一单，整单下载、逐行换源，上次没找到的那几首会被记住 ---- */
        const musicFavItems = ref([]);
        const musicFavMissing = ref(0);
        const musicFavSelected = ref([]);
        const musicFavSwitching = ref([]);
        const musicFavDownloading = ref(false);
        // 换源要求这一行的槽位里就住着真结果：只剩曲名的行没有「来路」可换，只能重新取址
        const musicFavReadySel = computed(() => (musicFavSelected.value || []).filter(r => r.resolved === 'ready'));

        async function loadMusicFavs() {
          try {
            const r = await api('/api/music/favorites');
            musicFavItems.value = r.items || [];
            musicFavMissing.value = r.missing || 0;
            musicFavSelected.value = [];
          } catch (e) {
            ElementPlus.ElMessage.error('收藏清单读取失败: ' + e.message);
          }
        }
        function onMusicFavSelection(rows) {
          musicFavSelected.value = rows || [];
        }
        async function addMusicFav(rows) {
          const list = (rows || []).filter(r => r && !r.reference_only && !r.is_local);
          if (!list.length) {
            ElementPlus.ElMessage.warning('无损参照和本地成品收不进收藏清单：这一单要能整单下');
            return;
          }
          try {
            const r = await api('/api/music/favorites', {
              method: 'POST',
              body: JSON.stringify({ rows: list.map(x => ({ ...x })) }),
              uiName: '收进收藏清单',
            });
            const bits = [`已收 ${r.added || 0} 首`];
            if (r.duplicated) bits.push(`${r.duplicated} 首清单里已有`);
            if (r.refused) bits.push(`${r.refused} 行是参照或本地成品、没收`);
            if (r.no_title) bits.push(`${r.no_title} 行没有曲名、没收`);
            const txt = bits.join('，') + `，清单共 ${r.total || 0} 首`;
            (r.added ? ElementPlus.ElMessage.success : ElementPlus.ElMessage.info)(txt);
            await loadMusicFavs();
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          }
        }
        async function removeMusicFav(rows) {
          const ids = (rows || []).map(r => r && r.id).filter(Boolean);
          if (!ids.length) return;
          try {
            const r = await api('/api/music/favorites/remove', {
              method: 'POST', body: JSON.stringify({ ids }), uiName: '从收藏清单删除',
            });
            ElementPlus.ElMessage.success(`已删除 ${r.removed} 首，清单还剩 ${r.total} 首`);
            await loadMusicFavs();
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          }
        }
        async function clearMusicFav() {
          const n = (musicFavItems.value || []).length;
          if (!n) return;
          try {
            await ElementPlus.ElMessageBox.confirm(
              `确定清空收藏清单里的 ${n} 首？只清这份清单，已经下载到目录里的文件不会被动。`,
              '清空收藏清单', { type: 'warning', confirmButtonText: '清空', cancelButtonText: '取消' });
          } catch (_) { return; }
          await removeMusicFav(musicFavItems.value);
        }
        function previewMusicFav(row) {
          playFrom(musicFavItems.value, row, 'fav');
        }
        async function switchMusicFav(rows) {
          const list = (rows || []).filter(r => r && r.slot && r.resolved === 'ready');
          if (!list.length) {
            ElementPlus.ElMessage.warning('勾选的行里没有可直接换源的歌 —— 「要重新找地址」的行先下这一次，会按曲名在「匹配源」里重新取址');
            return;
          }
          musicFavSwitching.value = musicFavSwitching.value.concat(list.map(r => r.slot));
          try {
            const r = await api('/api/music/switch_source', {
              method: 'POST',
              body: JSON.stringify({
                ids: list.map(x => x.slot),
                sources: (musicStrategy.value && musicStrategy.value.match_sources) || [],
                cookies: musicCookies.value || '',
              }),
              uiName: '收藏清单换源',
            });
            const fails = (r.results || []).filter(x => !x.ok)
              .map(x => `「${x.title || x.id}」—— ${x.reason || '其他源里没有过闸门的结果'}`);
            if (r.switched) {
              ElementPlus.ElMessage.success(`已换 ${r.switched} 首` + (fails.length ? `，${fails.length} 首没换成` : ''));
            } else {
              ElementPlus.ElMessage.warning(`都没换成：${fails.slice(0, 3).join('；') || '其他源里没有过闸门的结果'}`);
            }
            await loadMusicFavs();   // 换到的那条由后端同步进清单行
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          } finally {
            const gone = new Set(list.map(r => r.slot));
            musicFavSwitching.value = musicFavSwitching.value.filter(s => !gone.has(s));
          }
        }
        async function downloadMusicFav(rows) {
          const list = (rows && rows.length) ? rows : (musicFavItems.value || []);
          if (!list.length) return;
          musicFavDownloading.value = true;
          try {
            const r = await api('/api/music/favorites/download', {
              method: 'POST',
              body: JSON.stringify({
                ids: list.map(x => x.id),
                match_sources: (musicStrategy.value && musicStrategy.value.match_sources) || [],
                skip_downloaded: musicSkipExisting.value !== false,
                block_reupload: !!musicBlockReupload.value,
                quality_spec: musicQualityBody(),
                cookies: musicCookies.value || '',
              }),
              uiName: (rows && rows.length) ? '下载收藏清单勾选行' : '收藏清单整单下载',
            });
            ElementPlus.ElMessage.success((r.message || 'musicdl 下载中')
              + (r.reminted ? ` —— 其中 ${r.reminted} 首要先按曲名重新找地址` : ''));
            watchMusicBatch(r.started_at, { slots: r.slots || [] });
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          } finally {
            musicFavDownloading.value = false;
          }
        }
        // 整批跑完后把「没找到 / 本轮没轮到搜」的结论回填到清单：界面才知道哪几行要处理
        async function markMusicFavs(status, favCtx) {
          if (!favCtx) return;
          const m = (status && status.match) || {};
          try {
            await api('/api/music/favorites/mark', {
              method: 'POST', noLog: true,
              body: JSON.stringify({
                slots: favCtx.slots || [],
                missed: m.missed || [],
                unsearched: m.unsearched || [],
              }),
            });
          } catch (e) { return; }
          await loadMusicFavs();
        }
        async function installMusicdl() {
          if (installingMusicdl.value) return;
          installingMusicdl.value = true;
          const wasReady = musicdlReady.value;
          const oldVer = musicdlVersion.value;
          try {
            const r = await api('/api/music/install', {
              method: 'POST',
              body: JSON.stringify({ mirror: settings.value.pip_mirror || '', force: wasReady }),
            });
            ElementPlus.ElMessage.info(r.message || '正在后台处理 musicdl，进度见运行日志');
            let done = false;
            for (let i = 0; i < 20; i++) {
              await new Promise((res) => setTimeout(res, 5000));
              const st = await ensureMusicStatus().catch(() => null);
              if (st && st.musicdl && (st.musicdl_version || '') !== oldVer) {
                ElementPlus.ElMessage.success('musicdl ' + (wasReady ? '已更新' : '安装完成') + ' · v' + (st.musicdl_version || '?'));
                done = true;
                break;
              }
            }
            if (!done) {
              ElementPlus.ElMessage.info(
                wasReady ? '版本未变化，可能已是最新版；详情见运行日志' : '安装仍未完成，请查看运行日志中的 pip 输出'
              );
            }
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          } finally {
            installingMusicdl.value = false;
            ensureMusicStatus().catch(() => {});
          }
        }
        const SEARCH_PLAT_NAMES = { all: '全部平台', youtube: 'YouTube', bilibili: 'B站', douyin: '抖音' };
        const SEARCH_TYPE_NAMES = { all: '全部内容', video: '视频', channel: 'UP主/频道', playlist: '合集/播放列表' };
        const SORT_LABELS = { relevance: '相似度', views: '播放量', newest: '发布时间' };
        async function doSearch() {
          const q = (searchQuery.value || '').trim();
          if (!q) {
            ElementPlus.ElMessage.warning('请输入关键词');
            return;
          }
          searching.value = true;
          try {
            const data = await api('/api/search', {
              method: 'POST',
              body: JSON.stringify({
                query: q, platform: searchPlatform.value, content_type: searchContentType.value,
                limit: 100, sort: searchSort.value,
              }),
            });
            searchResults.value = data.results || [];
            searchTotal.value = data.total || searchResults.value.length;
            searchTruncated.value = !!data.truncated;
            searchNotes.value = data.notes || [];
            logAction(`聚合搜索「${q}」：取回 ${searchTotal.value} 条，显示 ${searchResults.value.length} 条`
                      + (searchNotes.value.length ? `，${searchNotes.value.length} 条空结果原因` : ''));
            if (!searchResults.value.length) {
              if (searchNotes.value.length) {
                ElementPlus.ElMessage.warning('没有可用结果，原因见下方提示');
              } else {
                ElementPlus.ElMessage.info('无结果');
              }
            }
          } catch (e) {
            searchNotes.value = [];
            ElementPlus.ElMessage.error(e.message);
          } finally {
            searching.value = false;
          }
        }
        function setSearchSort(v) {
          if (searchSort.value === v) return;
          searchSort.value = v;
          // 排序靠平台侧重新返回结果，前端不伪造顺序：已有结果时立即重搜
          if (searchResults.value.length) doSearch();
        }
        function normalizeSearchUrl(r) {
          if (!r) return '';
          let u = (r.url || '').trim();
          const id = (r.id || '').trim();
          const plat = (r.platform || '').toLowerCase();
          const ctype = (r.content_type || 'video').toLowerCase();
          if (u.startsWith('http')) return u;
          if (plat === 'youtube' && id) {
            if (ctype === 'playlist') return 'https://www.youtube.com/playlist?list=' + id;
            if (ctype === 'channel') return id.startsWith('UC') ? ('https://www.youtube.com/channel/' + id) : ('https://www.youtube.com/@' + id);
            return 'https://www.youtube.com/watch?v=' + id;
          }
          if (plat === 'bilibili' && id) {
            if (ctype === 'channel') return 'https://space.bilibili.com/' + id;
            if (ctype === 'playlist') return u || ('https://www.bilibili.com/bangumi/media/md' + id);
            return 'https://www.bilibili.com/video/' + id;
          }
          if (plat === 'douyin' && id) return 'https://www.douyin.com/video/' + id;
          if (plat === 'xiaohongshu' && id) return 'https://www.xiaohongshu.com/explore/' + id;
          if (id && /^[\w-]{6,}$/.test(id)) return 'https://www.youtube.com/watch?v=' + id;
          return u;
        }
        async function downloadSearchItem(r) {
          const u = normalizeSearchUrl(r);
          if (!u) {
            ElementPlus.ElMessage.warning('无可用链接');
            return;
          }
          urlText.value = u;
          page.value = 'home';
          await startDownload();
        }
        async function analyzeSearchItem(r) {
          const u = normalizeSearchUrl(r);
          if (!u) {
            ElementPlus.ElMessage.warning('无可用链接');
            return;
          }
          analyzeUrl.value = u;
          page.value = 'info';
          await analyzeFromInfoPage();
        }
        async function subscribeSearchItem(r) {
          const u = normalizeSearchUrl(r);
          if (!u) {
            ElementPlus.ElMessage.warning('无可用链接');
            return;
          }
          try {
            const title = (r && (r.title || r.uploader)) || '';
            const res = await api('/api/subs/add', {
              method: 'POST',
              body: JSON.stringify({ url: u, title })
            });
            const cnt = (res && res.init_count) || 0;
            ElementPlus.ElMessage.success(cnt ? `已订阅并索引 ${cnt} 条` : '已加入订阅');
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '订阅失败');
          }
        }
        async function exportSync() {
          try {
            const data = await api('/api/sync/export');
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = 'mediadownloader-sync.json';
            a.click();
            ElementPlus.ElMessage.success('已导出');
          } catch (e) {
            ElementPlus.ElMessage.error(e.message);
          }
        }
        function triggerImportSync() {
          if (syncFileInput.value) syncFileInput.value.click();
        }
        async function onImportSync(ev) {
          const f = ev.target.files && ev.target.files[0];
          if (!f) return;
          try {
            const text = await f.text();
            const data = JSON.parse(text);
            await api('/api/sync/import', {
              method: 'POST',
              body: JSON.stringify({ config: data.config, subscriptions: data.subscriptions, history: data.history, merge: true }),
            });
            ElementPlus.ElMessage.success('导入成功');
            await loadConfig();
            await loadSubs();
            await loadPlatformCookies();
            await loadMusicCookies();
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '导入失败');
          }
          ev.target.value = '';
        }


        async function openHistoryFile(row) {
          if (!row || !row.filepath) {
            ElementPlus.ElMessage.warning('无文件路径');
            return;
          }
          try {
            // 打开文件所在文件夹，避免直接请求文件内容导致 JSON.parse 错误
            await api('/api/open-folder', {
              method: 'POST',
              body: JSON.stringify({ path: row.filepath })
            });
            ElementPlus.ElMessage.success('已打开所在文件夹');
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '无法打开文件夹');
          }
        }

        async function redownload(row) {
          if (!row || !row.url) return;
          urlText.value = row.url;
          page.value = 'home';
          await startDownload();
        }

        const prevTaskStatus = ref({});
        function applyTaskList(list, running, paused) {
          // 完成通知
          for (const t of list) {
            const prev = prevTaskStatus.value[t.id];
            if (prev && prev !== 'finished' && t.status === 'finished') {
              notifyDone(t);
            }
            prevTaskStatus.value[t.id] = t.status;
          }
          tasks.value = list;
          status.value.running = running || 0;
          queuePaused.value = !!paused;
          const ids = new Set(list.map(t => t.id));
          selectedIds.value = selectedIds.value.filter(id => ids.has(id));
          const picked = new Set(selectedIds.value);
          const scope = visibleTasks.value;
          selectAll.value = scope.length > 0 && scope.every(t => picked.has(t.id));
        }

        // SSE 的 prog 帧带进度、速率、ETA、清晰度、字节数和封面，就地合并，免得整张表重渲染
        // 后端只在字段有值时才放进包，所以这里不能整行覆盖，否则会把已知的清晰度/大小擦没
        function applyTaskProg(rows) {
          if (!rows) return;
          for (const t of tasks.value) {
            const r = rows[t.id];
            if (r) Object.assign(t, r);
          }
        }

        async function loadTasks() {
          try {
            const sort = taskSort.value || 'queue';
            const data = await api('/api/tasks?sort=' + encodeURIComponent(sort));
            applyTaskList(data.tasks || [], data.running, data.paused);
            if (data.window) queueWindow.value = data.window;
            // 做种面板的数据只在「磁力 / 种子」页停留时按 30 秒顺带刷一次，别跟着 1.5 秒轮询敲 aria2
            if (page.value === 'bt' && Date.now() - lastSeedingAt > 30000) loadSeeding();
          } catch (_) {}
        }

        // ---------- SSE 推送：队列 / 日志 / 硬字幕 ----------
        let es = null;
        const sseOn = ref(false);

        function applySseLogs(items) {
          if (page.value !== 'log') return;
          const lv = logLevel.value, kw = (logSearch.value || '').toLowerCase();
          const keep = (items || []).filter(
            (e) => (lv === 'all' || !lv || e.level === lv) && (!kw || String(e.message || '').toLowerCase().includes(kw))
          );
          if (keep.length) logs.value = logs.value.concat(keep).slice(-200);
        }

        function startSSE() {
          if (!window.EventSource || es) return;
          try {
            es = new EventSource('/api/events');
          } catch (_) {
            return;
          }
          es.onopen = () => { sseOn.value = true; };
          es.onerror = () => { sseOn.value = false; };  // 浏览器会自动重连，这里只负责把轮询放回去
          es.addEventListener('state', (ev) => {
            try {
              const d = JSON.parse(ev.data);
              // 推送的永远是「队列」顺序，别的排序下不能拿它覆盖表格
              if (taskSort.value === 'queue') applyTaskList(d.tasks || [], d.running, d.paused);
              if (d.throttle) status.value.throttle = d.throttle;
              if (typeof d.pending === 'number') status.value.pending = d.pending;
              if (d.window) queueWindow.value = d.window;
            } catch (_) {}
          });
          es.addEventListener('prog', (ev) => {
            try { applyTaskProg(JSON.parse(ev.data).rows); } catch (_) {}
          });
          es.addEventListener('logs', (ev) => {
            try { applySseLogs(JSON.parse(ev.data)); } catch (_) {}
          });
          es.addEventListener('hardsub', (ev) => {
            try { applyBurnJobs(JSON.parse(ev.data)); } catch (_) {}
          });
        }

        function stopSSE() {
          if (es) { es.close(); es = null; }
          sseOn.value = false;
        }

        async function loadHistory() {
          try {
            const q = histSearch.value ? ('?q=' + encodeURIComponent(histSearch.value)) : '';
            const data = await api('/api/history' + q);
            history.value = data.history || [];
            histStats.value = data.stats || histStats.value;
          } catch (_) {}
        }

        async function loadLogs() {
          try {
            const params = new URLSearchParams({ level: logLevel.value, search: logSearch.value });
            const data = await api('/api/logs?' + params);
            logs.value = data.logs || [];
            logLoc.value = { dir: data.dir || '', file: data.file || 'app.log',
                             archives: data.archives || [] };
          } catch (_) {}
        }

        function applyPreset(name) {
          if (name === 'best') {
            opts.value.video_quality = 'best';
            opts.value.audio_quality = 'best';
            opts.value.format = 'mkv';
            opts.value.audio_only = false;
            opts.value.prefer_codec = 'auto';
          } else if (name === '1080') {
            opts.value.video_quality = '1080p';
            opts.value.audio_quality = '192k';
            opts.value.format = 'mp4';
            opts.value.audio_only = false;
            opts.value.prefer_codec = 'avc';
          } else if (name === 'small') {
            opts.value.video_quality = '720p';
            opts.value.audio_quality = '128k';
            opts.value.format = 'mp4';
            opts.value.audio_only = false;
            opts.value.prefer_codec = 'avc';
          } else if (name === 'audio') {
            opts.value.audio_only = true;
            opts.value.format = 'mp3';
            opts.value.audio_quality = '192k';
          } else if (name === 'archive') {
            opts.value.video_quality = 'best';
            opts.value.audio_quality = 'best';
            opts.value.format = 'mkv';
            opts.value.audio_only = false;
            opts.value.embed_meta = true;
            opts.value.embed_chapters = true;
            opts.value.embed_thumb = true;
            opts.value.write_info_json = true;
          }
          ElementPlus.ElMessage.success('已应用预设');
        }

        // 粘贴板里常见「一行挤好几个链接」或夹着中文说明，所以直接抓 http(s) 子串，不按行切
        // 磁力链和本地种子没有 http 前缀可抓，只能整行认：行首是 magnet: 或行尾是 .torrent
        function extractUrls(text) {
          const src = String(text || '');
          const found = src.match(/https?:\/\/[^\s"'<>，、；]+/g) || [];
          const out = [], seen = new Set();
          let dup = 0;
          for (const raw of found) {
            const u = raw.replace(/[)\]}>;,、，。；：:!?"']+$/, '');
            if (!u || seen.has(u)) { dup++; continue; }
            seen.add(u);
            out.push(u);
          }
          for (const line of src.split(/\r?\n/)) {
            const l = line.trim();
            if (!l || l.startsWith('http')) continue;
            if (!/^magnet:/i.test(l) && !/\.torrent$/i.test(l)) continue;
            const u = /^magnet:/i.test(l) ? l.split(/\s/)[0] : l;
            if (seen.has(u)) { dup++; continue; }
            seen.add(u);
            out.push(u);
          }
          return { urls: out, dup };
        }
        const urlPasteStat = computed(() => {
          const { urls, dup } = extractUrls(urlText.value);
          return { count: urls.length, dup };
        });

        async function pasteUrl() {
          try {
            const text = await navigator.clipboard.readText();
            if (text) urlText.value = (urlText.value ? urlText.value + '\n' : '') + text.trim();
          } catch {
            ElementPlus.ElMessage.warning('无法读取剪贴板，请手动粘贴');
          }
        }

        // 单行框里粘进「分享文案 + 链接」「一行挤好几条」会直接污染查询与解析，所以粘的那一刻就清一遍。
        // 口径与「粘贴」按钮、与 extractUrls 同一条，不再另写一套正则。
        function cleanPasted(text, kind) {
          const src = String(text || '');
          if (!src.trim()) return '';
          const firstLine = src.trim().split(/\r?\n/)[0].trim();
          if (kind === 'text') return firstLine.replace(/\s+/g, ' ');
          const { urls } = extractUrls(src);
          return urls[0] || firstLine;
        }

        // 右键「粘贴」与 Ctrl+V 都派发 paste 事件，所以只挂这一个处理函数。
        // 值写在事件目标（原生输入框）上，再补发 input 事件回灌 v-model：模板里取到的变量已被解包成字符串，
        // 拿它当 ref 赋 .value 是空操作。
        // 也不写成柯里形式 onPaste(box, 'url') 返回值 —— Vue 把带参数的表达式当语句执行，返回的函数会被丢掉。
        function onPaste(e, kind) {
          const cd = e.clipboardData || window.clipboardData;
          const text = cd && cd.getData ? cd.getData('text') : '';
          const v = cleanPasted(text, kind);
          if (!v) return;
          e.preventDefault();
          e.target.value = v;
          e.target.dispatchEvent(new Event('input', { bubbles: true }));
        }

        // 多行列表框（首页媒体链接 / 磁力 / 订阅 / 直播）不挂这里：
        // 它们的内容在解析时才归一（extractUrls / btParsed），粘进来的原文要留在框里给用户对着看。

        // ---------- Telegram 公开频道批量 ----------
        const dateShortcuts = [
          { text: '最近 7 天', value: () => { const e = new Date(), s = new Date(); s.setDate(s.getDate() - 6); return [s, e]; } },
          { text: '最近 30 天', value: () => { const e = new Date(), s = new Date(); s.setDate(s.getDate() - 29); return [s, e]; } },
          { text: '本月', value: () => { const e = new Date(); return [new Date(e.getFullYear(), e.getMonth(), 1), e]; } },
          { text: '上月', value: () => { const e = new Date(); return [new Date(e.getFullYear(), e.getMonth() - 1, 1), new Date(e.getFullYear(), e.getMonth(), 0)]; } },
        ];
        const tgChannel = ref('');
        const tgTypes = ref(['video']);
        const tgLimit = ref(60);
        const tgRange = ref([]);
        const tgBudget = ref(240);
        const tgSleep = ref(0.8);
        const tgListing = ref(false);
        const tgResults = ref([]);
        const tgSelected = ref([]);
        const tgDiag = ref({});
        const tgAudioOnly = ref(false);
        const tgMode = ref('anon');          // anon = t.me/s/ 匿名；mt = 登录后的账号会话
        const tgMt = ref({ installed: false, configured: false, logged_in: false, ack: [], user: null });
        const tgMtForm = ref({ api_id: '', api_hash: '', proxy: '', session_name: '' });
        const tgMtPhone = ref('');
        const tgMtCode = ref('');
        const tgMtPwd = ref('');
        const tgMtBusy = ref(false);
        const tgMtShowCred = ref(false);
        const tgSkipSeen = ref(true);
        const tgTypeOptions = [
          { value: 'video', label: '视频' },
          { value: 'audio', label: '音频文件' },
          { value: 'document', label: '文档' },
          { value: 'voice', label: '语音' },
          { value: 'photo', label: '图片' },
        ];
        const tgTypeMap = { video: '视频', audio: '音频文件', document: '文档', voice: '语音', photo: '图片' };
        const tgErrors = computed(() => Object.entries(tgDiag.value.errors || {}));
        const tgDownloadable = computed(() => tgResults.value.filter(r => r.downloadable));
        const tgProtectedRows = computed(() => tgResults.value.filter(r => r.protected));
        function tgTypeLabel(t) { return tgTypeMap[t] || t; }
        function tgRowSelectable(row) { return !!row.downloadable; }
        function onTgSelection(rows) { tgSelected.value = rows || []; }
        function clearTgResults() {
          tgResults.value = []; tgSelected.value = []; tgDiag.value = {};
        }
        async function loadTgMtStatus(loud) {
          try {
            const r = await api('/api/telegram/mt/status');
            tgMt.value = r || {};
            tgMtForm.value.api_id = r.api_id || '';
            tgMtForm.value.proxy = r.proxy || '';
            tgMtForm.value.session_name = r.session_name || '';
            tgSkipSeen.value = r.skip_seen !== false;
            if (!r.has_hash) tgMtForm.value.api_hash = '';
          } catch (e) {
            if (loud) ElementPlus.ElMessage.error('会话状态没拿到：' + String(e.message || e));
          }
        }
        async function saveTgMtConfig() {
          const f = tgMtForm.value;
          if (!String(f.api_id || '').trim() || !String(f.api_hash || '').trim()) {
            if (!tgMt.value.has_hash) {
              ElementPlus.ElMessage.warning('api_id 和 api_hash 都要填：去 my.telegram.org 用这个手机号申请');
              return;
            }
          }
          const body = { proxy: f.proxy || '', session_name: f.session_name || '' };
          if (f.api_id) body.api_id = f.api_id;
          if (f.api_hash) body.api_hash = f.api_hash;
          tgMtBusy.value = true;
          try {
            const r = await api('/api/telegram/mt/config', { method: 'POST', body: JSON.stringify(body) });
            ElementPlus.ElMessage.success(r.message || '已保存');
            tgMtForm.value.api_hash = '';
            await loadTgMtStatus(true);
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          } finally {
            tgMtBusy.value = false;
          }
        }
        async function tgMtSendCode() {
          tgMtBusy.value = true;
          try {
            const r = await api('/api/telegram/mt/send-code', {
              method: 'POST', body: JSON.stringify({ phone: tgMtPhone.value }),
            });
            if (!r.ok) { ElementPlus.ElMessage.error(r.message || '验证码没发出去'); return; }
            ElementPlus.ElMessage.success(
              `码已发到 ${r.phone}（${r.is_email ? '注册邮箱' : '手机上的 Telegram 客户端'}，${r.length} 位），填回来点「登录」`);
            await loadTgMtStatus(false);
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          } finally {
            tgMtBusy.value = false;
          }
        }
        async function tgMtSignIn() {
          if (!String(tgMtCode.value || '').trim()) {
            ElementPlus.ElMessage.warning('先点「发验证码」，再把收到的码填进来');
            return;
          }
          tgMtBusy.value = true;
          try {
            const r = await api('/api/telegram/mt/sign-in', {
              method: 'POST',
              body: JSON.stringify({ code: tgMtCode.value, password: tgMtPwd.value || '' }),
            });
            if (r.needs_password) {
              ElementPlus.ElMessage.warning(r.message || '该账号已开启两步验证：请填写云密码后再次点击登录');
              return;
            }
            if (!r.ok) { ElementPlus.ElMessage.error(r.message || '登录失败'); return; }
            const u = r.user || {};
            ElementPlus.ElMessage.success(`已登录：${u.name || u.phone || u.id || ''}`);
            tgMtCode.value = ''; tgMtPwd.value = '';
            await loadTgMtStatus(true);
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          } finally {
            tgMtBusy.value = false;
          }
        }
        async function tgMtLogout() {
          try {
            await ElementPlus.ElMessageBox.confirm(
              '退出将删除本机的 Telegram 会话文件，下次读取历史需重新接收验证码。凭据（api_id / api_hash）不会被删除。',
              '退出 Telegram 会话', { type: 'warning', confirmButtonText: '退出并删除会话', cancelButtonText: '取消' });
          } catch (_) { return; }
          tgMtBusy.value = true;
          try {
            const r = await api('/api/telegram/mt/logout', { method: 'POST', body: '{}' });
            ElementPlus.ElMessage.success(r.ok ? '已退出，本地会话已删除' : (r.message || '退出未完成'));
            await loadTgMtStatus(true);
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          } finally {
            tgMtBusy.value = false;
          }
        }
        function gotoSubsAdd() {
          subUrl.value = String(tgChannel.value || '').trim();
          subMode.value = tgMode.value === 'mt' ? 'mt' : '';
          page.value = 'subs';
        }
        async function listTgChannel() {
          if (!String(tgChannel.value || '').trim()) {
            ElementPlus.ElMessage.warning('请先填写频道名');
            return;
          }
          if (!(tgTypes.value || []).length) {
            ElementPlus.ElMessage.warning('至少选一种类型');
            return;
          }
          const isMt = tgMode.value === 'mt';
          if (isMt && !tgMt.value.logged_in) {
            tgMtShowCred.value = true;
            await loadTgMtStatus(true);
            if (!tgMt.value.logged_in) {
              ElementPlus.ElMessage.warning(tgMt.value.next_step || '先用上面的凭据框登录你的 Telegram 账号');
              return;
            }
          }
          tgListing.value = true;
          try {
            const common = {
              channel: tgChannel.value,
              limit: tgLimit.value,
              types: tgTypes.value,
              since: (tgRange.value && tgRange.value[0]) || '',
              until: (tgRange.value && tgRange.value[1]) || '',
              budget: tgBudget.value,
            };
            const r = isMt
              ? await api('/api/telegram/mt/list', {
                  method: 'POST', body: JSON.stringify({ ...common, skip_seen: tgSkipSeen.value }),
                })
              : await api('/api/telegram/list', {
                  method: 'POST', body: JSON.stringify({ ...common, page_sleep: tgSleep.value }),
                });
            if (r.ok === false && r.message) {
              tgResults.value = []; tgSelected.value = []; tgDiag.value = r.diag || {};
              tgMtShowCred.value = true;
              await loadTgMtStatus(false);
              ElementPlus.ElMessage.error(r.message);
              return;
            }
            tgResults.value = r.items || [];
            tgDiag.value = r.diag || {};
            tgSelected.value = [];
            if (!tgResults.value.length) {
              ElementPlus.ElMessage.warning((r.diag && r.diag.stopped) || '未列出条目');
            } else {
              ElementPlus.ElMessage.success(isMt
                ? `会话列出 ${tgResults.value.length} 条` + (tgProtectedRows.value.length
                    ? `，其中 ${tgProtectedRows.value.length} 条来自开启「限制保存内容」的频道` : '')
                : `列出 ${tgResults.value.length} 条，其中 ${tgDownloadable.value.length} 条可匿名下载`);
            }
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          } finally {
            tgListing.value = false;
          }
        }
        // 「限制保存内容」是频道主人的设置，只对第一次碰到的频道问一次，问过就记在配置里
        async function tgAckProtected(rows) {
          const acked = tgMt.value.ack || [];
          const pending = [...new Map(rows.filter(r => r.protected && !acked.includes(String(r.peer)))
            .map(r => [String(r.peer), r.channel || r.peer])).entries()];
          if (!pending.length) return true;
          const names = pending.map(([peer, name]) => `${name}（${peer}）`).join('、');
          try {
            await ElementPlus.ElMessageBox.confirm(
              `这些频道开启了「限制保存内容」：${names}。条目可以列出，但获取文件时 Telegram 很可能直接拒绝 —— `
              + '这是频道主人的设置，本工具不绕过该保护；被拒绝时会把原因如实写入任务。仍要逐条尝试吗？',
              '受限频道首次确认', { type: 'warning', confirmButtonText: '已知风险，继续', cancelButtonText: '暂不下载这些' });
          } catch (_) { return false; }
          for (const [peer] of pending) {
            try {
              const r = await api('/api/telegram/mt/ack', { method: 'POST', body: JSON.stringify({ peer }) });
              if (r && r.ack) tgMt.value.ack = r.ack;
            } catch (_) { /* 记不住下次再问，不影响入队 */ }
          }
          return true;
        }
        async function tgEnqueue(rows) {
          const isMt = tgMode.value === 'mt';
          const key = r => (isMt ? r.mt_url : r.url);
          const usable = (rows || []).filter(r => r && r.downloadable && key(r));
          const urls = [...new Set(usable.map(key))];
          if (!urls.length) {
            ElementPlus.ElMessage.warning(isMt
              ? '选中的条目没有可下载的链接，请先重新列出历史'
              : '选中的条目匿名无法获取直链，请切换到「使用账号会话」后重试');
            return;
          }
          if (isMt && !(await tgAckProtected(usable))) return;
          try {
            const r = await api('/api/download', {
              method: 'POST',
              body: JSON.stringify({
                urls,
                ...opts.value,
                audio_only: !!(tgAudioOnly.value || opts.value.audio_only),
                allow_playlist: !isMt,
              }),
            });
            const mergedPosts = usable.length - urls.length;
            ElementPlus.ElMessage.success(
              `已入队 ${r.added} 条` + (isMt ? '（走 Telegram 账号会话）' : '帖子')
              + (!isMt && mergedPosts ? ` · 同帖多视频合并掉 ${mergedPosts} 条` : '')
              + (r.merged ? ` · 去掉重复 ${r.merged} 条` : '')
              + (r.skipped ? ` · ${r.skipped} 条链接无效被忽略` : ''));
            page.value = 'queue';
            loadTasks();
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          }
        }
        function downloadTgSelected() { tgEnqueue(tgSelected.value); }
        function downloadTgRow(row) { tgEnqueue([row]); }
        function openTgRow(row) { window.open(row.url, '_blank', 'noopener'); }
        async function copyTgUrls() {
          const text = tgResults.value.map(r => r.url).join('\n');
          try {
            await navigator.clipboard.writeText(text);
            ElementPlus.ElMessage.success(`已复制 ${tgResults.value.length} 条帖子链接`);
          } catch (e) {
            ElementPlus.ElMessage.error('浏览器拒绝了剪贴板写入，可从表格里逐条打开');
          }
        }

        // ---------- 磁力 / 种子（aria2）----------
        const torrentFileInput = ref(null);
        const torrentUploading = ref(false);
        const aria2Checking = ref(false);
        const aria2Installing = ref(false);
        const aria2Info = ref('');
        const seedingRows = ref([]);
        const seedingNote = ref('');
        const btFilesTask = ref('');
        const btFileRows = ref([]);
        const btSelecting = ref(false);
        let lastSeedingAt = 0;
        const btText = ref('');
        const btStarting = ref(false);
        const btSeedOnly = ref(false);
        // tracker 与限速的读数一律来自后端：界面不自己算，免得显示的和真正交给 aria2 的不是一套
        const btTrackerText = ref('点「读取现状」看下一个新任务会带上哪几条 tracker');
        const btTrackerNote = ref('');
        const btTrackerLoading = ref(false);
        const btTrackerRefreshing = ref(false);
        const btLimitTask = ref('');
        const btLimitDl = ref('');
        const btLimitUl = ref('');
        const btLimitApplying = ref(false);
        const btLimitResult = ref('');

        // 这一页只认磁力链接和本地种子：网页链接留在首页，混进来的行要当场说清为什么没算上
        const btParsed = computed(() => {
          const lines = String(btText.value || '').split(/\r?\n/).map(l => l.trim()).filter(Boolean);
          const urls = [];
          const seen = new Set();
          let dup = 0;
          for (const line of lines) {
            const u = /^magnet:/i.test(line) ? line.split(/\s/)[0] : line;
            if (!/^magnet:/i.test(u) && !/\.torrent$/i.test(u)) continue;
            if (seen.has(u)) { dup++; continue; }
            seen.add(u);
            urls.push(u);
          }
          return { urls, dup, ignored: lines.length - urls.length - dup };
        });
        const btLinkCount = computed(() => btParsed.value.urls.length);
        const btIgnoredCount = computed(() => btParsed.value.ignored + btParsed.value.dup);

        function btSourceLabel(t) {
          return String(t.url || '').toLowerCase().startsWith('magnet:') ? '磁力' : '种子';
        }
        function btPicked(t) {
          return (t.files || []).filter(f => f.selected).length;
        }
        const btPickCount = computed(() => btFileRows.value.filter(f => f.selected).length);
        const btPickSize = computed(() => btFileRows.value.filter(f => f.selected).reduce((a, f) => a + (f.size || 0), 0));
        function btPickAll(v) {
          btFileRows.value.forEach(f => { f.selected = v; });
        }
        function toggleBtFiles(t) {
          if (btFilesTask.value === t.id) {
            btFilesTask.value = '';
            return;
          }
          btFilesTask.value = t.id;
          // 复选状态存在本地副本里：任务列表每 1.5 秒重刷一次，直接改 t.files 会把勾选冲掉
          btFileRows.value = (t.files || []).map(f => ({ ...f }));
        }
        async function applyBtSelect(t) {
          const indices = btFileRows.value.filter(f => f.selected).map(f => f.index);
          if (!indices.length) {
            ElementPlus.ElMessage.warning('至少要勾选一个文件');
            return;
          }
          btSelecting.value = true;
          try {
            const r = await api('/api/torrent/select', {
              method: 'POST', uiName: '改选种子内文件',
              body: JSON.stringify({ task_id: t.id, indices }),
            });
            btFileRows.value = (r.files || []).map(f => ({ ...f }));
            ElementPlus.ElMessage.success(`已让 aria2 只下这 ${r.count} 个文件`);
            await loadTasks();
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          } finally {
            btSelecting.value = false;
          }
        }
        // ---------- 自动分类规则 ----------
        const btRuleTestName = ref('');
        const btRuleTesting = ref(false);
        const btRuleTested = ref('');
        function addBtRule() {
          settings.value.bt_auto_rules.push({ name: '', mode: 'contains', pattern: '', subdir: '', enabled: true });
        }
        function delBtRule(i) { settings.value.bt_auto_rules.splice(i, 1); }
        function moveBtRule(i, d) {
          const a = settings.value.bt_auto_rules, j = i + d;
          if (j < 0 || j >= a.length) return;
          const t = a[i]; a[i] = a[j]; a[j] = t;   // 顺序就是优先级，只能靠上下移调
        }
        async function testBtRule() {
          const v = (btRuleTestName.value || '').trim();
          if (!v) { ElementPlus.ElMessage.warning('先写一个种子名字，或贴一条磁力 / 种子链接'); return; }
          btRuleTesting.value = true;
          try {
            const isRef = /^magnet:/i.test(v) || /\.torrent$/i.test(v) || /^file:\/\//i.test(v);
            const r = await api('/api/torrent/rules/test', {
              method: 'POST', uiName: '试自动分类规则',
              body: JSON.stringify(isRef ? { url: v } : { name: v }),
            });
            btRuleTested.value = `${r.message}｜比的是「${r.name || '（此刻还没有名字）'}」，来源：${r.name_from}`;
          } catch (e) {
            btRuleTested.value = '试匹配没走通：' + String(e.message || e);
          } finally {
            btRuleTesting.value = false;
          }
        }
        // aria2 少回一个键就少说一段：没量到的数不能替它写成 0，「peer 0」会被读成「确实没连上人」。
        function seedTotals(s) {
          const p = [];
          if (s.uploaded !== undefined && s.uploaded !== null) p.push('已传 ' + formatSize(Number(s.uploaded)));
          if (s.share_ratio !== undefined && s.share_ratio !== null) p.push('比率 ' + Number(s.share_ratio).toFixed(2));
          if (s.seed_seconds !== undefined && s.seed_seconds !== null) p.push('做种 ' + formatDuration(s.seed_seconds));
          return p.join(' · ');
        }
        function seedReadout(s) {
          const p = [];
          if (s.upload_speed) p.push('↑' + formatSize(Number(s.upload_speed)) + '/s');
          if (s.num_peers !== undefined) p.push('连接 ' + s.num_peers);
          if (s.num_seeders !== undefined) p.push('做种者 ' + s.num_seeders);
          if (s.tracker_count !== undefined) p.push('tracker ' + s.tracker_count);
          return p.join(' · ');
        }
        async function loadSeeding() {
          lastSeedingAt = Date.now();
          try {
            const r = await api('/api/torrent/seeding');
            seedingRows.value = r.items || [];
            seedingNote.value = r.note || '';
          } catch (_) {
            seedingRows.value = [];
            seedingNote.value = '';
          }
        }
        async function stopSeed(target) {
          const body = target && target.gid ? { gids: [target.gid] } : { ids: [target.id] };
          try {
            const r = await api('/api/torrent/stop-seed', { method: 'POST', uiName: '停止做种', body: JSON.stringify(body) });
            ElementPlus.ElMessage.success(r.stopped ? `已停止 ${r.stopped} 项做种，已下载的文件不动` : (r.message || '没有点到在做种的任务'));
            await Promise.all([loadSeeding(), loadTasks()]);
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          }
        }
        async function stopAllSeeding() {
          try {
            await ElementPlus.ElMessageBox.confirm('停止全部做种？已下载的文件不会删除，之后不再上传。', '确认', { type: 'warning' });
          } catch (_) { return; }
          try {
            const r = await api('/api/torrent/stop-seed', { method: 'POST', uiName: '全部停止做种', body: JSON.stringify({ all: true }) });
            ElementPlus.ElMessage.success(`已停止 ${r.stopped} 项做种`);
            await loadSeeding();
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          }
        }
        async function checkAria2() {
          aria2Checking.value = true;
          try {
            const r = await api('/api/aria2/status');
            // 地址回的是真正连的那个（设置里留空时是默认的 6800），光说「可连接」不知道连的到底是谁
            const addr = String(r.rpc || '').replace(/^https?:\/\//, '').replace(/\/jsonrpc.*$/, '');
            const bits = [(r.online ? 'RPC 可连接' : 'RPC 无应答') + (addr ? `（${addr}）` : '')];
            bits.push(r.binary ? 'aria2c：' + String(r.binary).split(/[\\/]/).pop() : '未找到 aria2c');
            if (r.daemon && r.daemon.owned) bits.push('进程由本程序拉起（PID ' + r.daemon.pid + '）');
            bits.push(r.autostart ? '自动拉起已开' : '自动拉起已关');
            if (r.seeding) bits.push(`做种 ${r.seeding} 项`);
            // 拉不起来时把后端给的原因原样带上，别让用户对着「无应答」猜
            if (r.ensure && r.ensure.why) bits.push(r.ensure.why);
            aria2Info.value = bits.join(' · ');
          } catch (e) {
            aria2Info.value = '检测失败：' + String(e.message || e);
          } finally {
            aria2Checking.value = false;
          }
        }

        async function installAria2() {
          aria2Installing.value = true;
          try {
            const r = await api('/api/update/aria2', { method: 'POST' });
            ElementPlus.ElMessage.info(r.message || 'aria2c 安装已在后台开始');
            setTimeout(() => { checkAria2(); loadStatus(); loadComponents(); }, 15000);
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          } finally {
            aria2Installing.value = false;
          }
        }
        function btTrackerHead(r) {
          const src = r.sources || [];
          const okN = src.filter(s => s.ok).length;
          const bits = [`抓到的来源 ${okN}/${src.length} 个`, `手动 ${r.manual ? r.manual.length : 0} 条`,
            `下一个新任务带上 ${r.count} 条`, `上限 ${r.max === 0 ? '0（不注入）' : r.max}`];
          bits.push(r.auto_update ? '自动获取已开' : '自动获取已关');
          bits.push(r.cache_time ? '缓存于 ' + String(r.cache_time).replace('T', ' ') : '本机还没有缓存');
          return bits.join(' · ');
        }
        function btTrackerProblems(r) {
          const out = [];
          if (r.note) out.push(r.note);
          (r.sources || []).filter(s => !s.ok).forEach(s => {
            out.push(`${s.label || s.url}：${s.fetched ? (s.error || '这次没抓到') : '还没抓过'}`);
          });
          return out.join('；');
        }
        async function loadBtTrackers() {
          btTrackerLoading.value = true;
          try {
            const r = await api('/api/bt/trackers');
            btTrackerText.value = btTrackerHead(r);
            btTrackerNote.value = btTrackerProblems(r);
          } catch (e) {
            btTrackerText.value = '读取失败：' + String(e.message || e);
            btTrackerNote.value = '';
          } finally {
            btTrackerLoading.value = false;
          }
        }
        async function refreshBtTrackers() {
          btTrackerRefreshing.value = true;
          try {
            const r = await api('/api/bt/trackers/refresh', {
              method: 'POST', uiName: '立即获取 tracker 列表', body: JSON.stringify({}),
            });
            (r.failed || []).length
              ? ElementPlus.ElMessage.warning(r.message + `（${r.failed.length} 个来源没抓到）`)
              : ElementPlus.ElMessage.success(r.message);
            await loadBtTrackers();
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          } finally {
            btTrackerRefreshing.value = false;
          }
        }
        function toggleBtLimit(t) {
          if (btLimitTask.value === t.id) {
            btLimitTask.value = '';
            return;
          }
          btLimitTask.value = t.id;
          btLimitDl.value = '';
          btLimitUl.value = '';
          btLimitResult.value = '';
        }
        async function applyBtLimit(t) {
          const dl = String(btLimitDl.value || '').trim();
          const ul = String(btLimitUl.value || '').trim();
          if (!dl && !ul) {
            ElementPlus.ElMessage.warning('下载限速和上传限速至少填一个，填 0 表示取消限速');
            return;
          }
          btLimitApplying.value = true;
          try {
            const body = { task_id: t.id };
            if (dl) body.download = dl;
            if (ul) body.upload = ul;
            const r = await api('/api/bt/limit', {
              method: 'POST', uiName: '改任务限速', body: JSON.stringify(body),
            });
            // 后端回的是从 aria2 读回来的值，界面只报这个，不报用户刚敲的那串
            btLimitResult.value = (r.ok ? '已生效（aria2 读回）：' : '未确认生效：') + r.message;
            r.ok ? ElementPlus.ElMessage.success(r.message) : ElementPlus.ElMessage.warning(r.message);
            await loadTasks();
          } catch (e) {
            btLimitResult.value = '失败：' + String(e.message || e);
            ElementPlus.ElMessage.error(String(e.message || e));
          } finally {
            btLimitApplying.value = false;
          }
        }
        function pickTorrentFile() {
          if (torrentFileInput.value) torrentFileInput.value.click();
        }
        async function onTorrentFile(ev) {
          const f = ev.target.files && ev.target.files[0];
          ev.target.value = '';
          if (!f) return;
          if (!/\.torrent$/i.test(f.name)) {
            ElementPlus.ElMessage.warning('只能选择 .torrent 种子文件');
            return;
          }
          torrentUploading.value = true;
          try {
            const fd = new FormData();
            fd.append('file', f, f.name);
            const resp = await fetch('/api/torrent/upload', { method: 'POST', body: fd });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(friendlyError(data.detail || resp.statusText));
            btText.value = (btText.value.trim() ? btText.value.trim() + '\n' : '') + data.url;
            logAction('上传种子文件');
            ElementPlus.ElMessage.success(`种子「${data.name}」（${formatSize(data.size)}）已写入输入框，点「开始下载」入队`);
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          } finally {
            torrentUploading.value = false;
          }
        }

        async function pasteBt() {
          try {
            const text = await navigator.clipboard.readText();
            if (text) btText.value = (btText.value ? btText.value + '\n' : '') + text.trim();
          } catch {
            ElementPlus.ElMessage.warning('无法读取剪贴板，请手动粘贴');
          }
        }

        async function startBtDownload() {
          const { urls, dup, ignored } = btParsed.value;
          if (!urls.length) {
            ElementPlus.ElMessage.warning(ignored + dup
              ? `输入的 ${ignored + dup} 行里没有磁力链接或本地种子路径`
              : '请粘贴 magnet: 链接，或点「上传种子」选择本地 .torrent 文件');
            return;
          }
          const seedOnly = btSeedOnly.value;
          btStarting.value = true;
          try {
            const r = await api('/api/download', {
              method: 'POST',
              body: JSON.stringify({ urls, ...opts.value, torrent_seed_only: seedOnly }),
            });
            btText.value = '';
            btSeedOnly.value = false;
            const merged = dup + (r && r.merged ? r.merged : 0);
            ElementPlus.ElMessage.success(
              `已交给 aria2 ${r && r.added != null ? r.added : (r.ids || []).length} 个任务`
              + (seedOnly ? ' · 按「只做种」挂上，已有成品不会被重新下载' : '')
              + (merged ? ` · 已合并 ${merged} 条重复` : '')
              + (r && r.skipped ? ` · ${r.skipped} 条不是磁力链接或种子，被忽略` : '')
            );
            await Promise.all([loadTasks(), loadSeeding()]);
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          } finally {
            btStarting.value = false;
          }
        }

        async function startDownload() {
          const { urls, dup } = extractUrls(urlText.value);
          if (!urls.length) {
            ElementPlus.ElMessage.warning('请输入至少一个有效 URL');
            return;
          }
          if ((opts.value.embed_sub || opts.value.write_sub_files) && !subLangList.value.length) {
            ElementPlus.ElMessage.warning('请至少选择一种字幕语言，或取消勾选「嵌入字幕 / 写出外挂字幕文件」');
            return;
          }
          syncSubLangsToOpts();
          submitting.value = true;
          try {
            const r = await api('/api/download', {
              method: 'POST',
              body: JSON.stringify({ urls, ...opts.value }),
            });
            urlText.value = '';
            const merged = dup + (r && r.merged ? r.merged : 0);
            ElementPlus.ElMessage.success(
              `已加入 ${r && r.added != null ? r.added : (r.ids || []).length} 个任务`
              + (merged ? ` · 已合并 ${merged} 条重复` : '')
              + (r && r.skipped ? ` · ${r.skipped} 条链接无效被忽略` : '')
            );
            const argNotes = (r && r.arg_notes) || [];
            if (argNotes.length) {
              ElementPlus.ElMessage.warning('「自定义 yt-dlp 参数」有 ' + argNotes.length + ' 项没生效：'
                + argNotes.slice(0, 3).join('；') + (argNotes.length > 3 ? ' 等' : ''));
            }
            page.value = 'queue';
            await loadTasks();
          } catch (e) {
            ElementPlus.ElMessage.error(e.message);
          } finally {
            submitting.value = false;
          }
        }

        async function stopAll() {
          await api('/api/stop', { method: 'POST' });
          ElementPlus.ElMessage.info('已停止');
          await loadTasks();
        }

        async function retryFailed() {
          await api('/api/retry', { method: 'POST' });
          await loadTasks();
        }
        const pluginsInfo = ref('');
        async function reloadPlugins() {
          try {
            const r = await api('/api/plugins/reload', { method: 'POST', body: '{}' });
            pluginsInfo.value = `已加载 ${r.count || 0} 个`;
            ElementPlus.ElMessage.success(pluginsInfo.value);
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          }
        }
        async function editTaskHeaders() {
          const id = selectedIds.value[0];
          if (!id) return;
          try {
            const { value } = await ElementPlus.ElMessageBox.prompt(
              '可填 Cookie 一行（name=value; ...）或 JSON：{"cookie":"...","referer":"...","url":"...","restart":true}',
              '修改任务 Cookie / Header / URL',
              { inputValue: 'cookie=', confirmButtonText: '应用', inputPlaceholder: 'cookie=... 或 JSON' }
            );
            let body = {};
            const raw = (value || '').trim();
            if (raw.startsWith('{')) {
              try { body = JSON.parse(raw); } catch (_) {
                ElementPlus.ElMessage.error('JSON 无效');
                return;
              }
            } else if (raw.toLowerCase().startsWith('cookie=')) {
              body = { cookie: raw.slice(7).trim(), restart: true };
            } else if (raw.includes('=') && (raw.includes(';') || raw.split('=').length === 2)) {
              body = { cookie: raw, restart: true };
            } else {
              ElementPlus.ElMessage.error('请输入 Cookie 字符串或 JSON');
              return;
            }
            body.id = id;
            const r = await api('/api/tasks/edit', { method: 'POST', body: JSON.stringify(body) });
            ElementPlus.ElMessage.success(r.applied === 'restarted' ? '已更新并重试' : '已保存参数');
          } catch (e) {
            if (e !== 'cancel' && e !== 'close') ElementPlus.ElMessage.error(String(e.message || e));
          }
        }
        async function retrySelected() {
          for (const id of selectedIds.value) {
            try {
              await api('/api/retry-one', { method: 'POST', body: JSON.stringify({ ids: [id] }) });
            } catch (_) {}
          }
          ElementPlus.ElMessage.success('已提交重试');
          await loadTasks();
        }
        async function cleanupParts() {
          try {
            const data = await api('/api/cleanup-parts', { method: 'POST', body: '{}' });
            ElementPlus.ElMessage.success(`已清理 ${data.removed || 0} 个临时文件`);
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '清理失败');
          }
        }
        function importUrlFile() {
          if (urlFileInput.value) urlFileInput.value.click();
        }
        function onUrlFile(ev) {
          const f = ev.target.files && ev.target.files[0];
          if (!f) return;
          const reader = new FileReader();
          reader.onload = () => {
            const text = String(reader.result || '');
            const { urls: lines, dup } = extractUrls(text);
            if (!lines.length) {
              ElementPlus.ElMessage.warning('文件中未找到有效链接');
              return;
            }
            const cur = urlText.value.trim();
            urlText.value = cur ? (cur + '\n' + lines.join('\n')) : lines.join('\n');
            ElementPlus.ElMessage.success(`已导入 ${lines.length} 条链接` + (dup ? ` · 跳过 ${dup} 条重复` : ''));
          };
          reader.readAsText(f);
          ev.target.value = '';
        }
        async function exportHistory() {
          window.open('/api/history/export', '_blank');
        }
        // 桌面通知不能只弹一下就完：点它要回到刚下完的那条卡片，否则用户还得自己在队列里翻
        const flashTaskId = ref('');
        let flashTimer = 0;
        function gotoTask(id, isBt) {
          const key = isBt ? 'btTasks' : 'queueTasks';
          const list = isBt ? btTasks.value : queueTasks.value;
          const idx = list.findIndex(t => String(t.id) === String(id));
          page.value = isBt ? 'bt' : 'queue';
          logAction('通知跳转：' + (isBt ? '磁力 / 种子' : '队列'));
          if (idx < 0) {
            ElementPlus.ElMessage.warning('这个任务已经不在列表里了，可能已被清掉');
            return;
          }
          pagers[key].page = Math.floor(idx / LIST_PAGE_SIZE) + 1;
          // 切页时 .content 正在放 translateY 入场动画，这段时间里 smooth 滚动会被浏览器静默丢弃
          setTimeout(() => {
            const el = document.getElementById('task-' + id);
            if (el) el.scrollIntoView({ block: 'start' });
          }, 120);
          flashTaskId.value = String(id);
          clearTimeout(flashTimer);
          flashTimer = setTimeout(() => { flashTaskId.value = ''; }, 2600);
        }
        function notifyDone(task) {
          try {
            if (!('Notification' in window)) return;
            if (Notification.permission !== 'granted') {
              if (Notification.permission !== 'denied') Notification.requestPermission();
              return;
            }
            const id = String(task.id);
            const opts = {
              body: task.title !== '等待中...' ? task.title : task.url,
              tag: 'dl-done-' + id,
            };
            if (task.thumbnail && !thumbBroken[id]) opts.icon = task.thumbnail;
            const n = new Notification('下载完成', opts);
            n.onclick = (ev) => {
              if (ev && ev.preventDefault) ev.preventDefault();
              try { n.close(); } catch (_) {}
              try { window.focus(); } catch (_) {}
              gotoTask(id, task.kind === 'torrent');
            };
          } catch (_) {}
        }

        async function clearFinished() {
          await api('/api/clear-finished', { method: 'POST' });
          await loadTasks();
        }

        function toggleSelect(id, checked) {
          if (checked) {
            if (!selectedIds.value.includes(id)) selectedIds.value.push(id);
          } else {
            selectedIds.value = selectedIds.value.filter(x => x !== id);
          }
          // 只看当前页：磁力任务勾满这一页就该点亮「全选」，不能被另一页的普通任务比下去
          const picked = new Set(selectedIds.value);
          selectAll.value = visibleTasks.value.length > 0 && visibleTasks.value.every(t => picked.has(t.id));
        }
        function toggleSelectAll(v) {
          if (v) selectedIds.value = visibleTasks.value.map(t => t.id);
          else selectedIds.value = [];
        }
        async function pauseSelected() {
          if (!selectedIds.value.length) return;
          await api('/api/pause', { method: 'POST', body: JSON.stringify({ ids: selectedIds.value }) });
          ElementPlus.ElMessage.info('已暂停选中任务');
          await loadTasks();
        }
        async function resumeSelected() {
          if (!selectedIds.value.length) return;
          await api('/api/resume', { method: 'POST', body: JSON.stringify({ ids: selectedIds.value }) });
          ElementPlus.ElMessage.success('已继续选中任务');
          await loadTasks();
        }
        async function deleteSelected() {
          if (!selectedIds.value.length) return;
          await api('/api/tasks/delete', { method: 'POST', body: JSON.stringify({ ids: selectedIds.value }) });
          selectedIds.value = [];
          selectAll.value = false;
          ElementPlus.ElMessage.success('已删除选中任务');
          await loadTasks();
        }
        async function pinSelected() {
          if (!selectedIds.value.length) return;
          await api('/api/tasks/pin', { method: 'POST', body: JSON.stringify({ ids: selectedIds.value }) });
          ElementPlus.ElMessage.success('已置顶');
          await loadTasks();
        }
        async function unpinSelected() {
          if (!selectedIds.value.length) return;
          await api('/api/tasks/unpin', { method: 'POST', body: JSON.stringify({ ids: selectedIds.value }) });
          ElementPlus.ElMessage.info('已取消置顶');
          await loadTasks();
        }
        async function moveTopSelected() {
          if (!selectedIds.value.length) return;
          await api('/api/tasks/top', { method: 'POST', body: JSON.stringify({ ids: selectedIds.value }) });
          ElementPlus.ElMessage.success('已移到队首');
          await loadTasks();
        }
        async function laterSelected() {
          if (!selectedIds.value.length) return;
          await api('/api/tasks/later', { method: 'POST', body: JSON.stringify({ ids: selectedIds.value }) });
          ElementPlus.ElMessage.info('已设为稍后下载');
          await loadTasks();
        }
        async function startLaterSelected() {
          if (!selectedIds.value.length) return;
          await api('/api/tasks/start-later', { method: 'POST', body: JSON.stringify({ ids: selectedIds.value }) });
          ElementPlus.ElMessage.success('已启动稍后任务');
          await loadTasks();
        }
        async function pauseAll() {
          await api('/api/pause', { method: 'POST', body: JSON.stringify({}) });
          ElementPlus.ElMessage.info('队列已暂停');
          await loadTasks();
        }
        async function resumeAll() {
          await api('/api/resume', { method: 'POST', body: JSON.stringify({}) });
          ElementPlus.ElMessage.success('队列已继续');
          await loadTasks();
        }
        async function resetThrottle(host) {
          try {
            const r = await api('/api/queue/throttle_reset', {
              method: 'POST',
              body: JSON.stringify({ host: host || '' }),
            });
            ElementPlus.ElMessage.success(r.cleared ? '已解除降速，队列继续调度' : '当前没有降速中的站点');
            await Promise.all([loadTasks(), loadStatus()]);
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          }
        }
        async function browsePath(mode, target) {
          try {
            const data = await api('/api/browse', {
              method: 'POST',
              body: JSON.stringify({ mode, title: mode === 'file' ? '选择文件' : '选择文件夹' }),
            });
            if (data.path) {
              const [root, key] = target.split('.');
              if (root === 'opts') opts.value[key] = data.path;
              else if (root === 'settings') settings.value[key] = data.path;
            }
          } catch (e) {
            ElementPlus.ElMessage.error('浏览失败: ' + e.message);
          }
        }

        const analyzing = ref(false);
        const analyzeUrl = ref('');

        async function doAnalyze(url) {
          if (!url || !url.startsWith('http')) {
            ElementPlus.ElMessage.warning('请输入有效 URL');
            return;
          }
          analyzing.value = true;
          try {
            mediaInfo.value = await api('/api/analyze', {
              method: 'POST',
              body: JSON.stringify({ url }),
            });
            analyzeUrl.value = url;
            // 换一次解析就是一批新条目，勾选和区间都按新列表重置，别拿上一个列表的序号来勾
            entrySel.value = [];
            infoCodec.value = '';
            selectedQuality.value = '';
            entryRange.value = { from: 1, to: (mediaInfo.value.entries || []).length || 1 };
            page.value = 'info';
            ElementPlus.ElMessage.success('解析完成');
          } catch (e) {
            ElementPlus.ElMessage.error('解析失败: ' + e.message);
          } finally {
            analyzing.value = false;
          }
        }

        async function analyze() {
          const { urls } = extractUrls(urlText.value);
          if (!urls.length) {
            ElementPlus.ElMessage.warning('请先在上方输入 URL');
            return;
          }
          const web = urls.find(u => /^https?:/i.test(u));
          if (!web) {
            ElementPlus.ElMessage.info('磁力链接与种子不需要解析，直接点「开始下载」即可');
            return;
          }
          await doAnalyze(web);
        }

        async function analyzeFromInfoPage() {
          await doAnalyze((analyzeUrl.value || '').trim());
        }

        async function pasteAnalyzeUrl() {
          try {
            const text = await navigator.clipboard.readText();
            const v = cleanPasted(text, 'url');
            if (v) analyzeUrl.value = v;
          } catch (_) {
            ElementPlus.ElMessage.warning('无法读取剪贴板');
          }
        }

        async function downloadFromInfo() {
          if (!mediaInfo.value || !mediaInfo.value.webpage_url) return;
          urlText.value = mediaInfo.value.webpage_url;
          if (mediaInfo.value.type === 'playlist') {
            opts.value.allow_playlist = true;
          }
          page.value = 'home';
          await startDownload();
        }

        async function downloadSpecificFormat(f) {
          if (!mediaInfo.value || !mediaInfo.value.webpage_url || !f) return;
          let fmt = String(f.format_id || '');
          // 纯视频轨自动拼 bestaudio，保证有声音
          if (f.vcodec && f.vcodec !== 'none' && (!f.acodec || f.acodec === 'none') && (!f.has_audio)) {
            fmt = `${fmt}+bestaudio/bestaudio`;
          }
          opts.value.force_format = fmt;
          opts.value.audio_only = !!(f.is_audio || (f.vcodec === 'none'));
          // 输出容器跟下载页的选择走（webm 源也能合并封装成 mkv），只有纯音频行才切 m4a/mp3
          if (opts.value.audio_only && (f.ext === 'm4a' || f.ext === 'mp3')) {
            opts.value.format = f.ext;
          }
          urlText.value = mediaInfo.value.webpage_url;
          ElementPlus.ElMessage.success(`将使用格式 ${fmt}`);
          page.value = 'home';
          await startDownload();
          // 用完清空，避免影响后续普通下载
          opts.value.force_format = '';
          opts.value.audio_only = false;
        }

        async function downloadQualityPreset(qp) {
          if (!mediaInfo.value || !mediaInfo.value.webpage_url || !qp) return;
          selectedQuality.value = qp.label || '';
          const audioQ = opts.value.audio_quality || 'best';
          opts.value.prefer_codec = qp.prefer_codec || 'auto';
          if (qp.height > 0) opts.value.video_quality = qp.height + 'p';
          else if (qp.height === 0) opts.value.video_quality = 'best';
          opts.value.audio_only = (qp.label === '仅音频' || qp.height === -1);
          if (opts.value.audio_only) {
            opts.value.format = 'm4a';
          }
          // 音频档位保持「最佳」时按解析出来的 format_id 精确下（和以往一致）；
          // 一旦指定了码率上限，改走后端 _resolve_format 的表达式，它才认 abr 过滤（仅音频同理）
          opts.value.force_format = audioQ === 'best' ? (qp.format_expr || qp.format_id || 'bv*+ba/b') : '';
          urlText.value = mediaInfo.value.webpage_url;
          ElementPlus.ElMessage.success('已选择：' + (qp.label || '') + (audioQ === 'best' ? '' : ' · 音频 ' + audioQ));
          page.value = 'home';
          await startDownload();
          opts.value.force_format = '';
          opts.value.audio_only = false;
        }

        async function downloadAllEntries() {
          if (!mediaInfo.value || !mediaInfo.value.entries || !mediaInfo.value.entries.length) return;
          const urls = mediaInfo.value.entries.map(e => e.url).filter(u => u && u.startsWith('http'));
          if (!urls.length) {
            // 无单条链接时整表下载
            urlText.value = mediaInfo.value.webpage_url || '';
            opts.value.allow_playlist = true;
            page.value = 'home';
            await startDownload();
            return;
          }
          urlText.value = urls.join('\n');
          opts.value.allow_playlist = false;
          page.value = 'home';
          await startDownload();
        }

        function onEntrySelection(rows) {
          entrySel.value = rows || [];
        }
        // 区间按播放列表自身的顺序取，弹层里先亮出首尾条目名，勾完再点下载不至于错一大片
        function entryAt(i) {
          const rows = (mediaInfo.value && mediaInfo.value.entries) || [];
          if (!rows.length) return '—';
          let n = Math.floor(Number(i) || 1);
          n = Math.min(Math.max(n, 1), rows.length);
          const r = rows[n - 1];
          const t = String((r && (r.title || r.id)) || '未命名').trim();
          return '第 ' + n + ' 条《' + (t.length > 20 ? t.slice(0, 20) + '…' : t) + '》';
        }
        function selectEntryRange() {
          const rows = (mediaInfo.value && mediaInfo.value.entries) || [];
          const tb = entryTableRef.value;
          if (!rows.length || !tb) return;
          let a = Math.floor(Number(entryRange.value.from) || 1);
          let b = Math.floor(Number(entryRange.value.to) || rows.length);
          if (a > b) { const t = a; a = b; b = t; }
          a = Math.min(Math.max(a, 1), rows.length);
          b = Math.min(Math.max(b, 1), rows.length);
          rows.forEach((r, i) => tb.toggleRowSelection(r, i + 1 >= a && i + 1 <= b));
          ElementPlus.ElMessage.success('已勾选第 ' + a + '–' + b + ' 条，共 ' + (b - a + 1) + ' 条');
        }
        function clearEntrySel() {
          if (entryTableRef.value) entryTableRef.value.clearSelection();
        }
        async function downloadSelectedEntries() {
          const rows = entrySel.value || [];
          if (!rows.length) return;
          const urls = rows.map(e => (e && e.url) || '').filter(u => u.startsWith('http'));
          if (!urls.length) {
            ElementPlus.ElMessage.warning('所选条目都没有单条链接，请改用「全部加入队列」整表下载');
            return;
          }
          if (urls.length < rows.length) {
            ElementPlus.ElMessage.warning('其中 ' + (rows.length - urls.length) + ' 条没有单条链接，已跳过');
          }
          urlText.value = urls.join('\n');
          opts.value.allow_playlist = false;
          page.value = 'home';
          await startDownload();
        }

        async function downloadEntry(row) {
          if (!row) return;
          const u = row.url || (row.id ? mediaInfo.value?.webpage_url : '');
          if (u && u.startsWith('http')) {
            urlText.value = u;
          } else if (row.id && mediaInfo.value?.webpage_url) {
            // 尽量拼出单条；否则用列表链接并允许 playlist
            urlText.value = mediaInfo.value.webpage_url;
            opts.value.allow_playlist = true;
          } else {
            ElementPlus.ElMessage.warning('该条目无可用链接');
            return;
          }
          page.value = 'home';
          await startDownload();
        }

        async function copyText(t) {
          try {
            await navigator.clipboard.writeText(t || '');
            ElementPlus.ElMessage.success('已复制');
          } catch (_) {
            ElementPlus.ElMessage.warning('复制失败');
          }
        }

        function copyFormats() {
          if (!mediaInfo.value || !mediaInfo.value.formats) return;
          const lines = mediaInfo.value.formats.map(f =>
            `${f.format_id}\t${f.resolution}\t${f.ext}\t${f.tbr}\t${f.vcodec}\t${f.acodec}\t${f.note || ''}`
          );
          copyText(['ID\t分辨率\t封装\t码率\t视频\t音频\t备注', ...lines].join('\n'));
        }

        async function loadFiles(subdir = '') {
          try {
            const q = subdir ? ('?subdir=' + encodeURIComponent(subdir)) : '';
            const data = await api('/api/files' + q);
            fileItems.value = data.items || [];
            filesPath.value = data.path || '';
            filesRoot.value = data.root || '';
          } catch (e) {
            ElementPlus.ElMessage.error('读取文件失败: ' + e.message);
          }
        }
        function onFileRowClick(row) {
          if (row.is_dir) {
            logAction('文件页进入目录：' + row.path);
            loadFiles(row.path);
          }
        }
        function openFile(path) {
          window.open('/api/files/open?path=' + encodeURIComponent(path), '_blank');
        }
        function goParentDir() {
          if (!filesPath.value) return;
          const parts = filesPath.value.replace(/\\/g, '/').split('/').filter(Boolean);
          parts.pop();
          const next = parts.join('/');
          logAction('文件页返回上级目录：' + (next || '根目录'));
          loadFiles(next);
        }
        async function deleteFile(row) {
          try {
            await ElementPlus.ElMessageBox.confirm(`确定删除 ${row.name}？`, '确认', { type: 'warning' });
            await api('/api/files/delete', { method: 'POST', body: JSON.stringify({ path: row.path }) });
            ElementPlus.ElMessage.success('已删除');
            await loadFiles(filesPath.value);
          } catch (_) {}
        }
        async function clearArchive() {
          try {
            await ElementPlus.ElMessageBox.confirm('清空后「跳过已下载」将失效，确定？', '确认', { type: 'warning' });
            await api('/api/files/clear-archive', { method: 'POST', body: '{}' });
            ElementPlus.ElMessage.success('已清空下载记录');
          } catch (e) {
            if (e && e.message) ElementPlus.ElMessage.error(e.message);
          }
        }
        function formatSize(n) {
          if (!n || n <= 0) return '0 B';
          const u = ['B', 'KB', 'MB', 'GB'];
          let i = 0;
          let x = n;
          while (x >= 1024 && i < u.length - 1) { x /= 1024; i++; }
          return x.toFixed(i ? 1 : 0) + ' ' + u[i];
        }
        // 卡片上的大小：下载中显「已下 / 总量」，完成或还不知道进度时只显总量；服务端没给总量就整块不显示
        function taskSize(t) {
          const total = Number(t && t.total_bytes) || 0;
          const done = Number(t && t.done_bytes) || 0;
          if (!total) return '';
          if (t.status === 'finished' || !done || done >= total) return formatSize(total);
          return formatSize(done) + ' / ' + formatSize(total);
        }
        // 卡片下方那行「清晰度 · 已下/总量」：服务端没给出流信息时整段不显示
        function taskSpec(t) {
          return [(t && t.res_label) || '', taskSize(t)].filter(Boolean).join(' · ');
        }
        function taskSpecTitle(t) {
          const bits = [];
          if (t && t.res_label) bits.push('实际下到的流：' + t.res_label);
          if (t && Number(t.total_bytes) > 0) bits.push('总量 ' + formatSize(t.total_bytes));
          return bits.join('，');
        }
        function tierRows(info, kind) {
          return ((info && info.tier_sizes) || []).filter(r => r && r.kind === kind);
        }
        // 视频档的实际体积：分流不带声音时，要再叠上当前「音频质量」档位那一份
        function videoTierBytes(info, tier, audioTier) {
          const v = tierRows(info, 'video').find(r => r.tier === tier);
          if (!v) return 0;
          let b = Number(v.bytes) || 0;
          if (!v.has_audio) {
            const rows = tierRows(info, 'audio');
            const a = rows.find(r => r.tier === audioTier) || rows.find(r => r.tier === 'best');
            b += Number(a && a.bytes) || 0;
          }
          return b;
        }
        // 相同体积的相邻档位并成一档：源里没有那一档时，实际下到的就是同一条流，两行数字没意义
        function tierSizeGroup(tiers, bytesOf) {
          const out = [];
          tiers.forEach(t => {
            const b = bytesOf(t);
            if (!b) return;
            const last = out[out.length - 1];
            if (last && last.b === b) last.ts.push(t);
            else out.push({ ts: [t], b });
          });
          const name = t => (t === 'best' ? '最佳' : t);
          return out.map(g => g.ts.map(name).join('/') + ' ≈' + formatSize(g.b)).join(' · ');
        }
        // 解析页的编码筛选：同一清晰度有多种编码时（4K 常见 AV1＋VP9）把它们摊开成可点的芯片；
        // 「最佳画质」「仅音频」两枚不参与筛选，任何时候都在
        const infoCodecOptions = computed(() => {
          const ps = (mediaInfo.value && mediaInfo.value.quality_presets) || [];
          const seen = [];
          ps.forEach(p => {
            if (!p || !(p.height > 0) || !p.codec_family) return;
            if (!seen.some(s => s.value === p.prefer_codec)) seen.push({ value: p.prefer_codec, label: p.codec_family });
          });
          return seen.length > 1 ? [{ value: '', label: '全部编码' }].concat(seen) : [];
        });
        const shownQualityPresets = computed(() => {
          const ps = (mediaInfo.value && mediaInfo.value.quality_presets) || [];
          if (!infoCodec.value || !infoCodecOptions.value.length) return ps;
          return ps.filter(p => p && (!(p.height > 0) || p.prefer_codec === infoCodec.value));
        });
        const infoAudioTop = computed(() => {
          const a = (mediaInfo.value && mediaInfo.value.audio_abrs) || [];
          return a.length ? Math.round(a[0]) + 'k' : '—';
        });
        // 每档画质的预估体积，显示在解析结果的「按清晰度选择」下面
        const tierSizeText = computed(() => {
          const info = mediaInfo.value;
          if (!info || !(info.tier_sizes || []).length) return '';
          const aq = opts.value.audio_quality || 'best';
          const bits = [];
          const vid = tierSizeGroup(videoQualities, t => videoTierBytes(info, t, aq));
          if (vid) bits.push('视频＋音频：' + vid);
          const aud = tierSizeGroup(audioQualities, t => {
            const r = tierRows(info, 'audio').find(x => x.tier === t);
            return Number(r && r.bytes) || 0;
          });
          if (aud) bits.push('只下音频：' + aud);
          if (!bits.length) return '';
          return '各档预估体积（音频按「音频质量」当前档位 ' + aq + ' 计）：' + bits.join('；') + '；实际大小以下到的流为准';
        });
        // 播放量 / 粉丝数：折成中文习惯的万、亿；平台已格式化的字符串原样返回
        function formatCount(v) {
          const n = Number(v);
          if (!Number.isFinite(n) || n <= 0) return String(v == null ? '' : v);
          if (n >= 1e8) return (n / 1e8).toFixed(1) + '亿';
          if (n >= 1e4) return (n / 1e4).toFixed(1) + '万';
          return String(Math.round(n));
        }
        function formatDuration(sec) {
          const s = Math.max(0, Math.floor(Number(sec) || 0));
          const h = Math.floor(s / 3600);
          const m = Math.floor((s % 3600) / 60);
          const r = s % 60;
          if (h > 0) return `${h}:${String(m).padStart(2,'0')}:${String(r).padStart(2,'0')}`;
          return `${m}:${String(r).padStart(2,'0')}`;
        }

        async function clearHistory() {
          try {
            await ElementPlus.ElMessageBox.confirm('确定清空全部历史？', '确认', { type: 'warning' });
            await api('/api/history/clear', { method: 'POST' });
            await loadHistory();
          } catch (_) {}
        }

        async function clearLogs() {
          try {
            await ElementPlus.ElMessageBox.confirm('确定清空日志？', '确认', { type: 'warning' });
            await api('/api/logs/clear', { method: 'POST' });
            await loadLogs();
          } catch (_) {}
        }
        // 诊断包是发给别人看的：密钥和 Cookie 内容由后端摘掉，前端只负责把文件收下来
        async function exportDiagnostics() {
          const done = actionName('/api/diagnostics/export');
          const tip = ElementPlus.ElMessage({ message: '正在打包诊断信息，请稍候…', duration: 0 });
          try {
            const res = await fetch('/api/diagnostics/export', { method: 'POST' });
            if (!res.ok) {
              let msg = '';
              try { msg = (await res.json()).detail; } catch (_) { msg = res.statusText; }
              throw new Error(friendlyError(msg || ('导出失败（HTTP ' + res.status + '）')));
            }
            const blob = await res.blob();
            if (!blob.size) throw new Error('诊断包是空的，请查看运行日志中的原因');
            const cd = res.headers.get('content-disposition') || '';
            const name = (cd.match(/filename="?([^";]+)"?/) || [])[1] || 'diagnostics.zip';
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = name;
            a.click();
            URL.revokeObjectURL(url);
            ElementPlus.ElMessage.success('已导出 ' + name + '（密钥与 Cookie 内容不在包里）');
            logAction(done);
          } catch (e) {
            logAction(done + '（失败）', 'warning');
            ElementPlus.ElMessage.error(e.message || '导出诊断包失败');
          } finally {
            tip.close();
          }
        }
        // 日志和程序本体在同一个文件夹，报障时点这个按钮直接打开它取文件
        async function openLogDir() {
          if (!logLoc.value.dir) await loadLogs();
          if (!logLoc.value.dir) {
            ElementPlus.ElMessage.warning('还没拿到日志所在的文件夹，重启程序后再点一次');
            return;
          }
          try {
            const r = await api('/api/open-folder', {
              method: 'POST',
              uiName: '打开日志文件夹',
              body: JSON.stringify({ path: logLoc.value.dir })
            });
            ElementPlus.ElMessage.success('已在资源管理器中打开 ' + (r.path || logLoc.value.dir));
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || '无法打开日志文件夹');
          }
        }

        // AcoustID：改动即单独保存，不必点「保存设置」
        let _acoustidSaved = "";
        async function saveAcoustid() {
          const payload = {
            acoustid_api_key: settings.value.acoustid_api_key || "",
            acoustid_min_score: settings.value.acoustid_min_score,
          };
          const sig = JSON.stringify(payload);
          if (sig === _acoustidSaved) return;
          try {
            await api('/api/config', { method: 'POST', body: JSON.stringify(payload) });
            _acoustidSaved = sig;
            ElementPlus.ElMessage.success("AcoustID 设置已保存");
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          }
        }

        const glossaryStat = ref(null);
        let glossaryTimer = null;
        function checkGlossary(silent) {
          const text = settings.value.subtitle_glossary || '';
          if (glossaryTimer) clearTimeout(glossaryTimer);
          if (!text.trim()) { glossaryStat.value = null; return; }
          glossaryTimer = setTimeout(async () => {
            try {
              const r = await api('/api/subtitle/glossary_check', {
                method: 'POST', body: JSON.stringify({ text }),
              });
              glossaryStat.value = r;
              if (silent) return;
              if (r.bad && r.bad.length) ElementPlus.ElMessage.warning(`有 ${r.bad.length} 行没写「原文 -> 译文」，已跳过`);
              else ElementPlus.ElMessage.success(`术语表可用，共 ${r.count} 条`);
            } catch (e) {
              /* 格式体检失败不影响保存与翻译 */
            }
          }, 300);
        }
        watch(() => settings.value.subtitle_glossary, () => checkGlossary(true));

        const speedWinStat = ref(null);
        let speedWinTimer = null;
        function checkSpeedWindows(silent) {
          const text = settings.value.speed_windows || '';
          if (speedWinTimer) clearTimeout(speedWinTimer);
          if (!text.trim()) { speedWinStat.value = null; return; }
          speedWinTimer = setTimeout(async () => {
            try {
              const r = await api('/api/config/speed_windows/check', {
                method: 'POST', body: JSON.stringify({ text }), noLog: !!silent,
              });
              speedWinStat.value = r;
              if (silent) return;
              if (r.errors && r.errors.length) {
                ElementPlus.ElMessage.warning(`有 ${r.errors.length} 行看不懂：${r.errors[0]}`);
              } else {
                ElementPlus.ElMessage.success(
                  `认出 ${r.count} 档，${r.now} ${r.current ? '按「' + r.current_note + '」限速' : '未命中时段，按全局限速'}`);
              }
            } catch (e) {
              /* 格式体检失败不影响保存与下载 */
            }
          }, 300);
        }
        watch(() => settings.value.speed_windows, () => checkSpeedWindows(true));

        // 队列定时窗：queueWindow 是后端 window_status() 的原样，横幅和设置页的每队列一行都从它取
        const queueWindow = ref(null);
        const windowHeld = computed(() => {
          const w = queueWindow.value;
          if (!w) return null;
          const rows = [];
          if (w.open === false) rows.push({ name: '全局', resume_at: w.resume_at, held: w.held || 0 });
          (w.queues || []).forEach((q) => {
            if (q.windows && q.open === false) rows.push({ name: q.name, resume_at: q.resume_at, held: q.held || 0 });
          });
          return rows.length ? rows : null;
        });
        const queueRows = computed(() => (queueWindow.value && queueWindow.value.queues) || []);

        const runWinStat = ref(null);
        let runWinTimer = null;
        async function refreshRunWindow() {
          try {
            const r = await api('/api/config/run_window/check', { method: 'POST', body: '{}', noLog: true });
            if (r && r.live) queueWindow.value = r.live;
            return r;
          } catch (_) { return null; }
        }
        function checkRunWindows(silent) {
          const text = settings.value.run_window || '';
          if (runWinTimer) clearTimeout(runWinTimer);
          runWinTimer = setTimeout(async () => {
            try {
              const r = await api('/api/config/run_window/check', {
                method: 'POST', body: JSON.stringify({ text }), noLog: !!silent,
              });
              runWinStat.value = text.trim() ? r : null;
              if (r && r.live) queueWindow.value = r.live;
              if (silent) return;
              if (!text.trim()) { ElementPlus.ElMessage.success('留空 = 任何时候都能开新任务'); return; }
              if (r.errors && r.errors.length) {
                ElementPlus.ElMessage.warning(`有 ${r.errors.length} 行看不懂：${r.errors[0]}`);
              } else {
                ElementPlus.ElMessage.success(
                  `认出 ${r.count} 段，${r.now} ${r.open ? '现在能开新任务' : '现在关着，' + r.resume_at + ' 自动开'}`);
              }
            } catch (e) {
              /* 格式体检失败不影响保存 */
            }
          }, 300);
        }
        watch(() => settings.value.run_window, () => checkRunWindows(true));

        async function saveSettings(silent) {
          try {
            const r = await api('/api/config', {
              method: 'POST',
              body: JSON.stringify(settings.value),
            });
            opts.value.download_dir = settings.value.download_dir;
            await loadStatus();
            await refreshRunWindow();   // 刚存的定时窗立刻反映到横幅与每队列那一行
            loadEncoders();             // 降级链按已保存的编码偏好算，存完重拉一次读数（不阻塞保存）
            // 「自定义 yt-dlp 参数」里被拒绝或与界面冲突的项：参数串照旧存着，但要把没生效的点名出来
            const notes = (r && r.ydl_arg_notes) || [];
            if (notes.length && !silent) {
              ElementPlus.ElMessage.warning('已保存，其中 ' + notes.length + ' 项参数没生效：'
                + notes.slice(0, 3).join('；') + (notes.length > 3 ? ' 等' : ''));
            } else if (!silent) {
              ElementPlus.ElMessage.success('已保存');
            }
          } catch (e) {
            if (!silent) ElementPlus.ElMessage.error(e.message);
            throw e;
          }
        }

        /* 视频编码：探测读数走后端 /api/video/encoders，本机起不来的显卡编码器界面上直接说清原因。
           降级链是后端按「已保存的设置」算的，所以 saveSettings 里会再拉一次。 */
        const encoders = ref({ items: [], chain: [] });
        const encProbeBusy = ref(false);
        const encProbeText = ref('还没探测');
        async function loadEncoders(refresh) {
          encProbeBusy.value = true;
          encProbeText.value = refresh ? '正在逐个起一次 FFmpeg 试…' : encProbeText.value;
          try {
            const r = await api('/api/video/encoders' + (refresh ? '?refresh=1' : ''), { noLog: true });
            encoders.value = r || { items: [], chain: [] };
            if (!r || r.ok === false) {
              encProbeText.value = (r && r.message) || '读不到编码器状态';
              return;
            }
            const ok = (r.items || []).filter(i => i.available).map(i => i.label);
            encProbeText.value = '可用 ' + (ok.join(' / ') || '没有')
              + (r.probed_at ? '（' + new Date(r.probed_at * 1000).toLocaleTimeString() + ' 探测）' : '');
          } catch (e) {
            encoders.value = { items: [], chain: [] };
            encProbeText.value = '探测失败：' + (e && e.message ? e.message : e);
          } finally {
            encProbeBusy.value = false;
          }
        }
        watch(page, p => { if (p === 'settings' && !(encoders.value.items || []).length) loadEncoders(); });

        /* 通知补发队列：后端先把通知写进 notify_outbox.json，再由后台线程按递增间隔重试，
           所以这里读的是「哪些还欠着、下次什么时候再试」，而不是「刚才发成功了没」。 */
        const outbox = ref({ records: [], counts: { pending: 0, sent: 0, dropped: 0 }, retry_delays: [] });
        const outboxBusy = ref(false);
        const outboxText = ref('');
        function applyOutbox(r, note) {
          outbox.value = {
            records: r.records || [],
            counts: r.counts || { pending: 0, sent: 0, dropped: 0 },
            retry_delays: r.retry_delays || [],
          };
          outboxText.value = note || '';
        }
        async function loadOutbox() {
          outboxBusy.value = true;
          try {
            const r = await api('/api/notify/outbox', { noLog: true });
            if (r && r.ok !== false) applyOutbox(r);
            else outboxText.value = (r && r.message) || '读不到补发队列';
          } catch (e) {
            outboxText.value = '读不到补发队列：' + (e && e.message ? e.message : e);
          } finally {
            outboxBusy.value = false;
          }
        }
        // 后端只把待发的推到「现在就试」并踢醒后台线程，发送本身不在这个请求里等
        async function retryOutbox() {
          outboxBusy.value = true;
          try {
            const r = await api('/api/notify/outbox/retry', { method: 'POST', noLog: true });
            if (r && r.ok !== false) applyOutbox(r, '已把 ' + (r.queued || 0) + ' 条排到最前，稍等一下再刷新看结果');
            else outboxText.value = (r && r.message) || '排不进队';
          } catch (e) {
            ElementPlus.ElMessage.error(e.message || e);
          } finally {
            outboxBusy.value = false;
          }
        }
        function clearOutbox() {
          ElementPlus.ElMessageBox.confirm('清空后待补发的通知不会再重试，已送出的记录也会一并抹掉。', '清空通知队列',
            { type: 'warning', confirmButtonText: '清空', cancelButtonText: '先不清' })
            .then(() => api('/api/notify/outbox/clear', { method: 'POST', noLog: true }))
            .then(() => { loadOutbox(); ElementPlus.ElMessage.success('已清空'); })
            .catch(e => { if (e && e.message) ElementPlus.ElMessage.error(e.message); });
        }
        function fmtWait(sec) {
          const s = Math.max(0, Number(sec) || 0);
          if (s < 60) return s + ' 秒';
          if (s < 3600) return Math.round(s / 60) + ' 分钟';
          return (s / 3600).toFixed(1) + ' 小时';
        }
        watch(page, p => { if (p === 'settings' && !(outbox.value.records || []).length) loadOutbox(); });
        watch(page, p => { if (p === 'settings') loadAuthStatus(true); });

        const mirrorOpts = ref({ github: [], pypi: [] });
        const mirrorProbing = ref('');
        function mirrorLabel(m) {
          const name = m.named || m.label || m.mirror || '直连';
          return m.ok ? name + ' · ' + m.ms + 'ms' : name + ' · 无法连接';
        }
        function mirrorHint(kind) {
          const rows = mirrorOpts.value[kind] || [];
          if (!rows.length) return '尚未测速：单击后将实测每个镜像的连通性与耗时';
          const ok = rows.filter(r => r.ok);
          return ok.length
            ? `可用 ${ok.length}/${rows.length} · 最快 ${ok[0].ms}ms（${ok[0].named || ok[0].label || '直连'}）`
            : `${rows.length} 个候选均无法连接，请检查网络或代理`;
        }
        async function probeMirrors(kind) {
          mirrorProbing.value = kind;
          try {
            const r = await api('/api/mirrors/probe?kind=' + kind);
            mirrorOpts.value = Object.assign({}, mirrorOpts.value, { [kind]: r.mirrors || [] });
            const ok = (r.mirrors || []).filter(m => m.ok);
            if (ok.length) {
              ElementPlus.ElMessage.success(`找到 ${ok.length} 个可用镜像，最快 ${ok[0].ms}ms，请在下拉中选择`);
            } else {
              ElementPlus.ElMessage.warning('这些镜像当前均无法连接');
            }
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          } finally {
            mirrorProbing.value = '';
          }
        }

        const netInfo = ref({ proxy_mode: 'auto', configured_proxy: '', system_proxy: '', system_proxy_source: '', platforms: [] });
        const netBusy = ref(false);

        async function loadNetInfo() {
          try {
            netInfo.value = await api('/api/net/info');
          } catch (e) {
            /* 拉不到只是设置页少一行结论，不打扰用户 */
          }
        }

        function netVerdictText(v) {
          return v === 'proxy' ? '走代理' : v === 'direct' ? '强制直连' : '跟随系统';
        }

        function netOverrideValue(row) {
          if (row.override === true) return 'proxy';
          if (row.override === false) return 'direct';
          return 'auto';
        }

        async function setProxyOverride(row, val) {
          const m = { ...(settings.value.proxy_by_platform || {}) };
          if (val === 'auto') delete m[row.key];
          else m[row.key] = val === 'proxy';
          settings.value.proxy_by_platform = m;
          try {
            await saveSettings(true);
            await loadNetInfo();
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          }
        }

        async function useSystemProxy() {
          netBusy.value = true;
          try {
            const r = await api('/api/net/use_system_proxy', { method: 'POST', body: '{}' });
            settings.value.proxy = r.proxy || '';
            netInfo.value = r.data || netInfo.value;
            ElementPlus.ElMessage.success(`已填入并启用系统代理 ${r.proxy}（来源：${r.source}）`);
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          } finally {
            netBusy.value = false;
          }
        }

        async function resetNetwork() {
          netBusy.value = true;
          try {
            const r = await api('/api/net/reset', { method: 'POST', body: '{}' });
            settings.value.proxy = '';
            settings.value.proxy_mode = 'auto';
            settings.value.proxy_by_platform = {};
            netInfo.value = r.data || netInfo.value;
            ElementPlus.ElMessage.success(
              `已清空：${(r.cleared || []).join('、') || '本来就是空的'}（平台 Cookie、下载历史都没动）`
            );
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          } finally {
            netBusy.value = false;
          }
        }

        const poStat = ref(null);
        const poChecking = ref(false);
        async function checkPoToken() {
          poChecking.value = true;
          try {
            await saveSettings(true);
            const r = await api('/api/po_token/check', { method: 'POST', body: '{}' });
            const chain = (r.chain || []).join('→') || '默认';
            const detail = String(r.detail || '');
            let text;
            if (!r.enabled) text = `门控未开启：按链 ${chain} 依次回退`;
            else if (r.ok) text = `PO 服务在线：${detail} · 链 ${chain}`;
            else text = `PO 服务没响应：${detail.slice(0, 40)} · 链 ${chain}`;
            if (r.note) text += ` · ${r.note}`;
            text += ` · TLS ${r.impersonate ? (r.fingerprints || []).join('→') : '模拟已关闭'}`;
            poStat.value = { ok: !r.enabled || !!r.ok, text };
            if (!r.enabled || r.ok) ElementPlus.ElMessage.success(text);
            else ElementPlus.ElMessage.warning(text);
          } catch (e) {
            ElementPlus.ElMessage.error(String(e.message || e));
          } finally {
            poChecking.value = false;
          }
        }

        function statusType(s) {
          return { finished: 'success', failed: 'danger', downloading: 'primary', queued: 'info', stopped: 'warning', paused: 'warning', later: 'info' }[s] || 'info';
        }
        function statusLabel(s) {
          return { finished: '完成', failed: '失败', downloading: '下载中', queued: '排队', stopped: '已停止', paused: '已暂停', later: '稍后' }[s] || s;
        }

        watch(page, (p) => {
          logAction('切换到「' + (pageTitle.value || p) + '」');
          const c = document.querySelector('.content');
          if (c) {
            c.classList.remove('is-enter');
            void c.offsetWidth; // 不强制回流，同名动画不会重放
            c.classList.add('is-enter');
          }
          if (p === 'queue' || p === 'live' || p === 'bt') loadTasks();
          if (p === 'bt') { loadSeeding(); loadBtTrackers(); }
          if (p === 'live') loadLiveMonitors();
          if (p === 'history') loadHistory();
          if (p === 'log') loadLogs();
          if (p === 'files') loadFiles(filesPath.value || '');
          if (p === 'subs') loadSubs();
          if (p === 'sniff') loadCatcatch();
          if (p === 'favs') loadFavTab();
          if (p === 'music') loadMusicFavs();
          if (p === 'settings') { loadPlatformCookies(); loadMusicCookies(); loadRiskPresets(); loadComponents(); loadNetInfo(); }
          if (p === 'tg') loadTgMtStatus(false);
        });

        watch(tgMode, (m) => {
          clearTgResults();
          if (m === 'mt') { tgMtShowCred.value = !tgMt.value.logged_in; loadTgMtStatus(true); }
        });

        onMounted(async () => {
          const paintIcons = () => {
            try {
              if (window.lucide && lucide.createIcons) lucide.createIcons({ attrs: { 'stroke-width': 2 } });
            } catch (_) {}
          };
          paintIcons();
          setTimeout(paintIcons, 200);
          watch(page, () => setTimeout(paintIcons, 50));
          window.addEventListener('keydown', onSpaceKey);

          loadLibrary(false);
          loadTranscodePresets();

          await loadAuthStatus(true);   // 先问「这台设备要不要登录」，被挡住就直接弹登录窗
          await loadAuthStatus(true);   // 先问一次门的状态：非本机又没登录时直接弹登录窗，别让后面一路 401
          await loadConfig();
          await loadStatus();
          ensureMusicStatus().catch(() => {});   // 一进页面就知道 musicdl 是否内置，决定「安装」按钮显不显示
          bootCompCheck();                        // 读后端的上游版本检测结果：有新版弹一次，侧栏「设置」标橙点
          try {
            if ('Notification' in window && Notification.permission === 'default') {
              Notification.requestPermission();
            }
          } catch (_) {}
          startSSE();
          let pollTick = 0;
          pollTimer = setInterval(() => {
            pollTick = (pollTick + 1) % 8;
            // SSE 正常时表格/日志走推送，轮询退成 ~12 秒一次的兜底（连接半死也能纠回来）
            const catchup = pollTick === 0;
            if (!sseOn.value || catchup) {
              if (page.value === 'queue' || page.value === 'live' || status.value.running > 0) loadTasks();
              if (page.value === 'queue' && (status.value.running > 0 || (status.value.throttle || []).length)) loadStatus();
              if (page.value === 'log') loadLogs();
            }
            if (page.value === 'live') loadLiveMonitors();
          }, 1500);
        });
        onUnmounted(() => { if (pollTimer) clearInterval(pollTimer); if (pipelineTimer) clearInterval(pipelineTimer); if (burnTimer) clearInterval(burnTimer); if (musicBatchTimer) clearInterval(musicBatchTimer); window.removeEventListener('keydown', onSpaceKey); stopSSE(); });

        /* ---- 这三张 el-table 原先用 Element 内部排序：一旦分页就只能排当前页，改成全量排序 ---- */
        const FAV_DIR = { title: 'asc', uploader: 'asc', platform: 'asc' };
        const FAV_GETTERS = { title: x => x.title || '', uploader: x => x.uploader || '', platform: x => x.platform || '' };
        const favSort = ref({ key: '', dir: 'asc' });
        const favSorted = computed(() => applySort(favItems.value, favSort.value, FAV_GETTERS));
        function onFavSortChange({ prop, order }) {
          if (!order) return;
          favSort.value = nextSort(favSort.value, prop, order, FAV_DIR);
          logSort('收藏列表', favSort.value.key, favSort.value.dir);
        }

        const MUSIC_GETTERS = { title: x => x.title || '', artists: x => x.artists || '', album: x => x.album || '' };
        const musicSort = ref({ key: '', dir: 'asc' });
        const musicSorted = computed(() => applySort(musicResults.value, musicSort.value, MUSIC_GETTERS));
        function onMusicSortChange({ prop, order }) {
          if (!order) return;
          musicSort.value = nextSort(musicSort.value, prop, order, {});
          logSort('音乐搜索结果', musicSort.value.key, musicSort.value.dir);
        }

        const TG_DIR = { date: 'desc', title: 'asc' };
        const TG_GETTERS = { date: x => x.date || '', title: x => x.title || '' };
        const tgSort = ref({ key: '', dir: 'asc' });
        const tgSorted = computed(() => applySort(tgResults.value, tgSort.value, TG_GETTERS));
        function onTgSortChange({ prop, order }) {
          if (!order) return;
          tgSort.value = nextSort(tgSort.value, prop, order, TG_DIR);
          logSort('Telegram 内容', tgSort.value.key, tgSort.value.dir);
        }

        /* ---- 超长列表统一分页：每页 50 条，翻页只换切片，排序与筛选始终作用于全量 ---- */
        const pagers = {
          queueTasks: usePager(() => queueTasks.value),
          btTasks: usePager(() => btTasks.value),
          files: usePager(() => filteredFiles.value),
          history: usePager(() => historySorted.value),
          search: usePager(() => searchResults.value),
          music: usePager(() => musicSorted.value),
          tg: usePager(() => tgSorted.value),
          fav: usePager(() => favSorted.value),
          musicFav: usePager(() => musicFavItems.value),
          subs: usePager(() => subsSorted.value),
          library: usePager(() => librarySorted.value),
          sniff: usePager(() => sniffDisplayItems.value),
          liveMon: usePager(() => liveMonitors.value),
          liveTasks: usePager(() => liveTasks.value),
        };
        /* 整组换新结果时回到第一页（ref 只在被替换时触发，改单条字段不会）；
           队列 / 历史 / 订阅靠轮询刷新，不能重置，否则用户正在看的那一页会被弹走。 */
        watch(searchResults, () => { pagers.search.page = 1; });
        watch(musicResults, () => { pagers.music.page = 1; });
        watch(tgResults, () => { pagers.tg.page = 1; });
        watch(favItems, () => { pagers.fav.page = 1; });
        watch(libraryItems, () => { pagers.library.page = 1; });
        watch(sniffItems, () => { pagers.sniff.page = 1; });
        watch(fileSearch, () => { pagers.files.page = 1; });
        /* 搜索条件切换本身不发请求，自动埋点抓不到，这里单独留痕 */
        watch([searchPlatform, searchContentType, searchSort], () => {
          logAction(`聚合搜索条件：${SEARCH_PLAT_NAMES[searchPlatform.value] || searchPlatform.value}`
            + ` / ${SEARCH_TYPE_NAMES[searchContentType.value] || searchContentType.value}`
            + ` / 按${SORT_LABELS[searchSort.value] || searchSort.value}`);
        });

        return {
          page, navs, navGroups, CREDITS, appVersion, queueStat, subNewTotal, navBadge, navDot, pageTitle, urlText, urlPasteStat, extractUrls, friendlyError, glossaryStat, checkGlossary, speedWinStat, checkSpeedWindows, queueWindow, windowHeld, queueRows, runWinStat, checkRunWindows, exportBilingual, exportBilingualSelected, pipelineRow, pipelineView, showPipeline, closePipeline, refreshPipeline, rerunStage, pipeStatusLabel, pipeStatusType, opts, videoQualities, audioQualities, formats, codecOptions,
          pagers, favSort, onFavSortChange, musicSort, onMusicSortChange, tgSort, onTgSortChange,
          subLangOptions, subLangList, selectAllSubLangs, clearSubLangs, toggleSubLang,
          selectedIds, selectAll, queuePaused, taskSort, sseOn, toggleSelect, toggleSelectAll,
          pauseSelected, resumeSelected, deleteSelected, pinSelected, unpinSelected, moveTopSelected, laterSelected, startLaterSelected, pauseAll, resumeAll, resetThrottle, poStat, poChecking, checkPoToken, browsePath, loadTasks,
          status, tasks, mediaInfo, fileItems, filesPath, filesRoot,
          history, histStats, histSearch, logs, logLevel, logSearch,
          settings, browserOptions, submitting, updatingYtdlp, updatingFfmpeg, updatingNm3u8, updatingWhisper, updateNm3u8, updateWhisper, downloadExtension,
          applyPreset,
          pasteUrl, onPaste, cleanPasted, startDownload, stopAll, retryFailed, retrySelected, editTaskHeaders, reloadPlugins, pluginsInfo, cleanupParts, clearFinished,
          downloadSpecificFormat, openHistoryFile,
          subs, subUrl, subMode, subIsTg, subAdding, subScanning, subBusy, subKindInfo, subKindMeta, subStatus, setSubAuto, subFirst, subAddCount, subAutoAdd, backfillSub, backfillRange, backfilling, openSubBackfill, closeSubBackfill, runSubBackfill, subPlanSub, subPlan, subPlanLoading, subPlanArch, openSubPlan, closeSubPlan, loadSubPlan, runSubPlanNow, clearSubArchive, ruleSub, ruleSaving, ruleForm, ruleSubIsTg, ruleSubIsMusic, subRuleQualities, subRuleFormats, openSubRules, closeSubRules, saveSubRules,
          liveUrl, liveTasks, liveTasksActive, liveRecordMinutes, liveDefaultMinutesText, liveAutoSaveText, liveMonitorUrl, liveMonitors, tgTesting,
          isLiveRunning, fileBasename, openLiveFile, clearFinishedLiveTasks,
          sniffUrl, sniffLoading, sniffItems, sniffSelected, sniffDone, sniffDisplayItems, sniffMergeLoading, canSniffMerge, runSniff, sniffSelectAll, sniffSelectNone, sniffDownloadSelected, sniffDownloadOne, sniffDownloadMerge, copyText, browserSniff, browserSniffPort, browserSniffLoading, startBrowserSniff, stopBrowserSniff, clearBrowserSniff, pollBrowserSniff,
          catcatch, catcatchFileInput, loadCatcatch, triggerCatcatchImport, onCatcatchConfig, toggleCatcatchRule, deleteCatcatchRule, clearCatcatchRules,
          libraryItems, libraryLoading, libraryFilter, libraryFiltered, librarySorted, libSort, LIB_DIR, libAudioText, loadLibrary, transcodePresets, runTranscode, openLibFolder,
          libQa, libQaLoading, libQaSpec, libQaTag, libQaDone, libQaLow, libQaUnknown, libQaMissing, libQaRefLow, checkLibraryQuality,
          toggleSort, sortIcon, cmp, onFileSortChange, historySorted, histSort, HIST_DIR, formatsSorted, fmtSort, FMT_DIR, subsSorted, subSort, SUB_DIR,
          gotoSubsAdd,
          tgChannel, tgTypes, tgTypeOptions, tgLimit, tgRange, dateShortcuts, tgBudget, tgSleep, tgListing, tgResults, tgSelected, tgDiag, tgAudioOnly, tgErrors, tgDownloadable, tgTypeLabel, tgRowSelectable, onTgSelection, clearTgResults, listTgChannel, downloadTgSelected, downloadTgRow, openTgRow, copyTgUrls,
          tgMode, tgMt, tgMtForm, tgMtPhone, tgMtCode, tgMtPwd, tgMtBusy, tgMtShowCred, tgSkipSeen, tgProtectedRows, loadTgMtStatus, saveTgMtConfig, tgMtSendCode, tgMtSignIn, tgMtLogout,

          wecomTesting, storageTesting, testStorage, riskPresets, favTab, favFolders, favFolderId, favItems, favSelected, favLoading, favMeta, ytPlaylistUrl,
          TG_DL_KEYS, TG_CH_KEYS, WECOM_DL_KEYS, WECOM_CH_KEYS, flagCount, flagAll, flagMixed, setFlags,
          biliQrLoading, biliQrUrl, biliQrKey, biliQrMsg, biliQrImage, biliQrCanvas, playerUrl, playerName, playerIsVideo, playerIsAudio,
          musicCookieItems, musicCookieText, ncQrLoading, ncQrUrl, ncQrKey, ncQrMsg, ncQrImage,
          loadMusicCookies, saveMusicCookie, clearMusicCookie, startNeteaseQr, pollNeteaseQr,
          mediaEl, transcriptBox, transcript, mediaCueIdx, onMediaTimeUpdate, seekToCue, fmtClock, speakerTagType,
          srtEdit, openSrtEditor, srtCloseEdit, srtDiscard, srtShiftSel, srtMerge, srtDrop, srtSave,
          srtEditBox, srtQc, runSrtQc, runSrtRewrap, qcJumpTo,
          searchQuery, searchPlatform, searchContentType, searchSort, setSearchSort,
          searchTotal, searchTruncated, searchNotes, SEARCH_PLAT_NAMES, searchResults, searching, platformCookies, cookieIssueCount, syncFileInput,
          musicKeyword, musicResults, musicSearching, musicSourceErrors, musicNeedsMatch, musicScoreLine, musicHasScore, musicdlVersion, musicdlReady, musicPreset, musicStrategy, saveMusicStrategy, musicSearchType, musicIncludeLocal, musicFilenameTemplate, musicEmbedMeta, musicSkipExisting, musicHideUnavailable, musicBlockReupload, musicIncludeReference, musicQualitySpec, musicQualityOptions, musicQualitySummary, refHint, matchHint, openRefLink, player, playerEl, playerPlaying, playerTime, playerDur, playerVol, playerMuted, playerSeeking, playerSeekVal, playerStep, playerToggle, playerClose, playerSeek, onPlayerTick, onPlayerMeta, onPlayerEnded, musicLrcLines, musicLrcActive, previewMusicRow, probeMusicRow, switchMusicSource, musicSwitching, scanLocalMusic, musicSources, musicSourceOptions, musicMatchSourceOptions, musicPresetOptions, musicSourceOrdered, musicPlaylistUrl, musicPlaylistMode, saveMusicPlaylistMode, musicCookies, musicSelected, aiPipeline, analyzeAudioFile, aiDemucs, aiTts, installVoicePkgs, loadVoiceStatus, toggleRealtime, installingVoice, voiceStatusText, rtRecording, rtTranslate, rtTargetLang, rtLog, searchMusic, batchSearchDownload, applyMusicPreset, parseMusicPlaylist, onMusicSelection, downloadMusicSelected, downloadMusicRow, showAlreadyHave, musicFavItems, musicFavMissing, musicFavSelected, musicFavReadySel, musicFavSwitching, musicFavDownloading, onMusicFavSelection, addMusicFav, removeMusicFav, clearMusicFav, previewMusicFav, switchMusicFav, downloadMusicFav, loadMusicFavs, installMusicdl,
          loadSubs, addSub, removeSub, toggleSub, scanOneSub, scanAllSubs, startLiveRecord, pauseLiveTask, resumeLiveTask, endLiveTask, endAllLive, cancelLiveTask, addLiveMonitor, removeLiveMonitor, pauseLiveMonitor, resumeLiveMonitor, scanLiveMonitors, loadLiveMonitors, liveRoomCfg, liveRoomFmts, liveRoomQualities, openLiveMonitorCfg, saveLiveMonitorCfg, liveMonitorCfgText, testTelegram,
          testWecom, applyRiskPreset, loadRiskPresets, loadFavTab, loadFavFolderItems, loadYtPlaylist, onFavSelChange,
          downloadFavSelected, downloadFavOne, subscribeFavSelected, subscribeFavOne, startBiliQr, pollBiliQr,
          isPlayable, isAudioFile, isMediaFile, isVideoFile, openPicard, mbTagFile, mbEnrichFile, fingerprintFile, guessTagsFile, isSrtFile, aiDemucs, aiTts, installVoicePkgs, loadVoiceStatus, toggleRealtime, installingVoice, voiceStatusText, rtRecording, rtTranslate, rtTargetLang, rtLog, aiTranscribe, aiTranslateSrt, aiCalibrateSrt, onFileSelectionChange, runBatchAi, runSrtCalibrateSelected,
          burnDlg, burnJob, burnStarting, burnSubChoices, burnOutName, burnRunning, burnPercent, burnStatusText, openBurn, closeBurn, startBurn, stopBurn,
          batchMode, batchScope, batchRunning, selectedFiles, syncOffsetSec, syncScale, syncInplace, playFile, zipPath, zipCurrentFolder,
          doSearch, downloadSearchItem, analyzeSearchItem, subscribeSearchItem, normalizeSearchUrl, loadPlatformCookies, savePlatformCookie, savePlatformCookieText, clearCookieFlag, browsePlatformCookie, exportSync, triggerImportSync, onImportSync,
          importUrlFile, onUrlFile, urlFileInput, exportHistory,
          torrentFileInput, torrentUploading, pickTorrentFile, onTorrentFile,
          btText, btStarting, btLinkCount, btIgnoredCount, pasteBt, startBtDownload,
          btTasks, queueTasks,
          aria2Checking, aria2Installing, aria2Info, checkAria2, installAria2,
          seedingRows, seedingNote, loadSeeding, stopSeed, stopAllSeeding, seedTotals, seedReadout,
          btRuleTestName, btRuleTesting, btRuleTested, addBtRule, delBtRule, moveBtRule, testBtRule,
          btFilesTask, btFileRows, btSelecting, btSourceLabel, btPicked, btPickAll,
          btPickCount, btPickSize, toggleBtFiles, applyBtSelect,
          btSeedOnly, btTrackerText, btTrackerNote, btTrackerLoading, btTrackerRefreshing,
          loadBtTrackers, refreshBtTrackers,
          btLimitTask, btLimitDl, btLimitUl, btLimitApplying, btLimitResult, toggleBtLimit, applyBtLimit,
          analyzing, analyzeUrl, analyze, analyzeFromInfoPage, pasteAnalyzeUrl,
          downloadFromInfo, downloadEntry, downloadQualityPreset, downloadAllEntries, entryTableRef, entrySel, entryRange, onEntrySelection, entryAt, selectEntryRange, clearEntrySel, downloadSelectedEntries, selectedQuality, infoCodec, infoCodecOptions, shownQualityPresets, infoAudioTop, copyText, copyFormats,
          loadFiles, onFileRowClick, openFile, goParentDir, deleteFile, clearArchive, formatSize, taskSize, taskSpec, taskSpecTitle, tierSizeText, thumbBroken, flashTaskId, formatCount, formatDuration,
          fileSearch, fileSort, filteredFiles, runFileAction, openDownloadFolder, testCookie, redownload, toggleDark,
          UI_THEMES, setTheme,
          loadStatus, checkEnv, updateYtdlp, updateFfmpeg,
          components, compInfo, updatingComp, latestBusy, verCmp, loadComponents, updateComponent, pathBusy, setEnvPath,
          compAll, compAllBusy, compTargets, compAllSummary, updateAllComponents,
          compUpdates, compCheckBusy, compCheckText, startCompCheck,
          encoders, encProbeBusy, encProbeText, loadEncoders,
          outbox, outboxBusy, outboxText, loadOutbox, retryOutbox, clearOutbox, fmtWait,
          auth, authGate, authForm, authBusy, authTokenShown,
          loadAuthStatus, doLogin, saveAuthKnobs, applyAuthPassword,
          copyMachineToken, rotateMachineToken, unlockIp, unlockAll,
          loadHistory, loadLogs, clearHistory, clearLogs, openLogDir, exportDiagnostics, logLoc, saveSettings, saveAcoustid,
          mirrorOpts, mirrorProbing, mirrorLabel, mirrorHint, probeMirrors,
          netInfo, netBusy, loadNetInfo, netVerdictText, netOverrideValue, setProxyOverride,
          useSystemProxy, resetNetwork,
          statusType, statusLabel,
        };
      },
    }).use(ElementPlus, { locale: window.ElementPlusLocaleZhCn }).mount('#app');

    /* 动态光源：光标停在卡片哪一侧，高光与投影就往反方向倒。
       只给当前 hover 的那张卡片写变量，并用 rAF 合帧，避免 pointermove 逐事件重算样式。 */
    (() => {
      const reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
      const PROPS = ['--lx', '--ly', '--sx', '--sy'];
      let cur = null, last = null, raf = 0;
      const clear = () => {
        if (cur) PROPS.forEach(p => cur.style.removeProperty(p));
        cur = null;
      };
      const paint = () => {
        raf = 0;
        if (!cur || !last) return;
        const r = cur.getBoundingClientRect();
        if (!r.width || !r.height) return;
        const clamp = v => Math.max(-1, Math.min(1, v));
        const nx = clamp(((last.clientX - r.left) / r.width - .5) * 2);
        const ny = clamp(((last.clientY - r.top) / r.height - .5) * 2);
        cur.style.setProperty('--lx', nx.toFixed(3));
        cur.style.setProperty('--ly', ny.toFixed(3));
        cur.style.setProperty('--sx', (50 + nx * 50).toFixed(1) + '%');
        cur.style.setProperty('--sy', (50 + ny * 50).toFixed(1) + '%');
      };
      document.addEventListener('pointermove', (e) => {
        if (reduce.matches) { clear(); return; }
        const el = e.target;
        const card = el && el.closest ? el.closest('.card') : null;
        if (card !== cur) { clear(); cur = card; }
        if (!cur) return;
        last = e;
        if (!raf) raf = requestAnimationFrame(paint);
      }, true);
    })();
  