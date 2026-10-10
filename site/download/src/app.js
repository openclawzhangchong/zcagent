(function () {
  "use strict";

  var live = document.getElementById("live");

  function announce(msg) {
    if (live) live.textContent = msg;
  }

  function fallbackCopy(text) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.top = "-1000px";
    document.body.appendChild(ta);
    ta.select();
    var ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (err) {
      ok = false;
    }
    document.body.removeChild(ta);
    return ok;
  }

  document.querySelectorAll("[data-copy]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var value = btn.getAttribute("data-copy");
      var done = function (ok) {
        var original = btn.textContent;
        btn.textContent = ok ? "已复制" : "复制失败";
        announce(ok ? "已复制到剪贴板" : "复制失败，请手动选择文本");
        window.setTimeout(function () {
          btn.textContent = original;
        }, 1800);
      };

      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(value).then(
          function () {
            done(true);
          },
          function () {
            done(fallbackCopy(value));
          }
        );
      } else {
        done(fallbackCopy(value));
      }
    });
  });
})();
