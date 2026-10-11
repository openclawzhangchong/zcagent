package main

// WebView2's built-in context menu offers Back / Reload / Save image as / Print,
// and its labels come from the Edge runtime -- we can neither relabel nor drop
// individual entries. Turning it off and drawing the two entries we do want is
// the only way to get "上一页 / 重新加载系统" without "另存为 / 打印".
//
// Runs on the remote dashboard origin too, so it must not depend on the Wails
// runtime; history and location are plain DOM.

const contextMenuMarker = "data-octop-context-menu"

func contextMenuJS() string {
	return `(function(){
		if (document.documentElement.dataset.octopMenuReady === '1') return;
		document.documentElement.dataset.octopMenuReady = '1';
		var MARKER = '` + contextMenuMarker + `';
		var COPY = {
			zh: { back: '上一页', reload: '重新加载系统' },
			en: { back: 'Back', reload: 'Reload' }
		};
		var open = null;
		function copy() {
			var lang = (document.documentElement.lang || '').toLowerCase();
			return lang.indexOf('zh') === 0 ? COPY.zh : COPY.en;
		}
		function close() {
			if (open && open.parentNode) open.parentNode.removeChild(open);
			open = null;
		}
		function entry(label, enabled, run) {
			var el = document.createElement('div');
			el.textContent = label;
			el.style.cssText = 'padding:7px 14px;font-size:13px;line-height:1.4;border-radius:6px;' +
				'color:' + (enabled ? '#111827' : '#9ca3af') + ';' +
				'cursor:' + (enabled ? 'pointer' : 'default') + ';' +
				'user-select:none;white-space:nowrap;';
			if (enabled) {
				el.addEventListener('mouseenter', function(){ el.style.background = '#eef1f4'; });
				el.addEventListener('mouseleave', function(){ el.style.background = 'transparent'; });
				el.addEventListener('click', function(){ close(); run(); });
			}
			return el;
		}
		function show(x, y) {
			close();
			var t = copy();
			var menu = document.createElement('div');
			menu.setAttribute(MARKER, '');
			menu.style.cssText = 'position:fixed;z-index:2147483647;min-width:132px;padding:4px;' +
				'background:#fff;border:1px solid #e5e7eb;border-radius:9px;' +
				'box-shadow:0 6px 24px rgba(0,0,0,.16);' +
				'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Noto Sans SC",sans-serif;';
			menu.appendChild(entry(t.back, history.length > 1, function(){ history.back(); }));
			menu.appendChild(entry(t.reload, true, function(){ location.reload(); }));
			document.body.appendChild(menu);
			var rect = menu.getBoundingClientRect();
			menu.style.left = Math.max(4, Math.min(x, window.innerWidth - rect.width - 6)) + 'px';
			menu.style.top = Math.max(4, Math.min(y, window.innerHeight - rect.height - 6)) + 'px';
			open = menu;
		}
		window.addEventListener('contextmenu', function(event) {
			if (event.button !== 2) return;
			event.preventDefault();
			event.stopPropagation();
			show(event.clientX, event.clientY);
		}, true);
		window.addEventListener('pointerdown', function(event) {
			if (open && !(open.contains && open.contains(event.target))) close();
		}, true);
		window.addEventListener('keydown', function(event) {
			if (event.key === 'Escape') close();
		}, true);
		window.addEventListener('wheel', close, true);
		window.addEventListener('blur', close);
	})();`
}
