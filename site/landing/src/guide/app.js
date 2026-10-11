/* /guide 的交互：目录折叠 + 当前章节高亮。
   渐进增强：脚本不跑时，目录与锚点仍然是可读可点的普通链接。 */

(function () {
  "use strict";

  var toggle = document.querySelector(".guide-nav-toggle");
  var nav = document.querySelector(".guide-nav");
  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      var open = nav.getAttribute("data-open") !== "false";
      nav.setAttribute("data-open", open ? "false" : "true");
      toggle.setAttribute("aria-expanded", open ? "false" : "true");
    });
  }

  var links = Array.prototype.slice.call(document.querySelectorAll('.guide-nav a[href^="#"]'));
  var sections = links
    .map(function (link) {
      return document.getElementById(link.getAttribute("href").slice(1));
    })
    .filter(Boolean);

  if (!sections.length || !("IntersectionObserver" in window)) return;

  function setCurrent(id) {
    links.forEach(function (link) {
      var active = link.getAttribute("href") === "#" + id;
      if (active) {
        link.setAttribute("aria-current", "true");
      } else {
        link.removeAttribute("aria-current");
      }
    });
  }

  // 取当前视口里最靠上的那一节；短页滚动到底时保持最后一节。
  var visible = new Map();
  var observer = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          visible.set(entry.target.id, entry.boundingClientRect.top);
        } else {
          visible.delete(entry.target.id);
        }
      });
      if (!visible.size) return;
      var top = Infinity;
      var id = null;
      visible.forEach(function (value, key) {
        if (value < top) {
          top = value;
          id = key;
        }
      });
      if (id) setCurrent(id);
    },
    { rootMargin: "-84px 0px -60% 0px", threshold: 0 }
  );

  sections.forEach(function (section) {
    observer.observe(section);
  });
})();
