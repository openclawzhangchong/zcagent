// 智策官网 — progressive enhancement only. The page is fully readable with
// JS disabled; this adds the menu, the tabs and copy-to-clipboard.

(function () {
  "use strict";

  var live = document.getElementById("live");

  function announce(msg) {
    if (live) live.textContent = msg;
  }

  /* ------------------------------------------------------------- menu */

  var toggle = document.querySelector(".menu-toggle");
  var menu = document.getElementById("menu");

  function setMenu(open) {
    if (!toggle || !menu) return;
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute("aria-label", open ? "关闭菜单" : "打开菜单");
    menu.hidden = !open;
  }

  if (toggle && menu) {
    toggle.addEventListener("click", function () {
      setMenu(toggle.getAttribute("aria-expanded") !== "true");
    });
    menu.addEventListener("click", function (e) {
      if (e.target.closest("a")) setMenu(false);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") setMenu(false);
    });
  }

  /* -------------------------------------------------------- topbar shadow */

  var topbar = document.querySelector(".topbar");
  if (topbar) {
    var onScroll = function () {
      topbar.classList.toggle("is-stuck", window.scrollY > 8);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  /* --------------------------------------------------------------- tabs */

  var group = document.querySelector("[data-tabs]");
  if (group) {
    var tabs = Array.prototype.slice.call(group.querySelectorAll('[role="tab"]'));
    var panels = tabs.map(function (tab) {
      return document.getElementById(tab.getAttribute("aria-controls"));
    });

    var select = function (index) {
      tabs.forEach(function (tab, i) {
        var on = i === index;
        tab.classList.toggle("is-active", on);
        tab.setAttribute("aria-selected", String(on));
        if (panels[i]) panels[i].hidden = !on;
      });
    };

    tabs.forEach(function (tab, i) {
      tab.addEventListener("click", function () {
        select(i);
      });
      tab.addEventListener("keydown", function (e) {
        var next = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : -1;
        if (next < 0) return;
        e.preventDefault();
        var target = tabs[(next + tabs.length) % tabs.length];
        target.focus();
        select(tabs.indexOf(target));
      });
    });
  }

  /* --------------------------------------------------------------- copy */

  function flash(btn, label) {
    var original = btn.textContent;
    btn.textContent = label;
    btn.classList.add("is-done");
    window.setTimeout(function () {
      btn.textContent = original;
      btn.classList.remove("is-done");
    }, 1600);
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    // Cloudflare Pages serves over https, but a plain-http preview should
    // still work, so keep the textarea fallback.
    return new Promise(function (resolve, reject) {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      var ok = false;
      try {
        ok = document.execCommand("copy");
      } catch (e) {
        ok = false;
      }
      document.body.removeChild(ta);
      ok ? resolve() : reject(new Error("copy failed"));
    });
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".copy");
    if (!btn) return;

    var text = btn.getAttribute("data-copy");
    if (!text) {
      var sel = btn.getAttribute("data-copy-target");
      var pre = sel && document.querySelector(sel);
      text = pre ? pre.innerText.replace(/\s+$/, "") : "";
    }
    if (!text) return;

    copyText(text).then(
      function () {
        flash(btn, "已复制");
        announce("已复制到剪贴板");
      },
      function () {
        flash(btn, "复制失败");
        announce("复制失败，请手动选择文本");
      }
    );
  });
})();