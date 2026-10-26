(function () {
  var root = document.documentElement;
  var body = document.body;
  var sidebarToggle = document.querySelector("[data-sidebar-toggle]");
  var sidebarOverlay = document.querySelector("[data-sidebar-overlay]");
  var sidebar = document.getElementById("app-sidebar");
  var mobileQuery = window.matchMedia("(max-width: 767px)");

  function setMobileSidebarOpen(isOpen) {
    if (!body || !sidebarToggle) {
      return;
    }
    body.classList.toggle("mobile-sidebar-open", isOpen);
    sidebarToggle.setAttribute("aria-expanded", String(isOpen));
    sidebarToggle.setAttribute(
      "aria-label",
      isOpen ? "Close navigation" : "Open navigation",
    );
  }

  if (sidebarToggle && sidebar) {
    sidebarToggle.addEventListener("click", function () {
      if (mobileQuery.matches) {
        setMobileSidebarOpen(
          !body.classList.contains("mobile-sidebar-open"),
        );
        return;
      }

      var isCollapsed = root.classList.toggle("sidebar-collapsed");
      sidebarToggle.setAttribute("aria-expanded", String(!isCollapsed));
      sidebarToggle.setAttribute(
        "aria-label",
        isCollapsed ? "Expand sidebar" : "Collapse sidebar",
      );
      try {
        window.localStorage.setItem(
          "leaflens-sidebar-collapsed",
          String(isCollapsed),
        );
      } catch (error) {
        // Sidebar still works for this visit if storage is unavailable.
      }
    });

    if (sidebarOverlay) {
      sidebarOverlay.addEventListener("click", function () {
        setMobileSidebarOpen(false);
      });
    }

    sidebar.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("click", function () {
        if (mobileQuery.matches) {
          setMobileSidebarOpen(false);
        }
      });
    });

    function syncSidebarForViewport() {
      if (mobileQuery.matches) {
        setMobileSidebarOpen(false);
      } else {
        body.classList.remove("mobile-sidebar-open");
        sidebarToggle.setAttribute(
          "aria-expanded",
          String(!root.classList.contains("sidebar-collapsed")),
        );
        sidebarToggle.setAttribute(
          "aria-label",
          root.classList.contains("sidebar-collapsed")
            ? "Expand sidebar"
            : "Collapse sidebar",
        );
      }
    }

    if (mobileQuery.addEventListener) {
      mobileQuery.addEventListener("change", syncSidebarForViewport);
    } else {
      mobileQuery.addListener(syncSidebarForViewport);
    }
    syncSidebarForViewport();
  }

  var userMenu = document.querySelector("[data-user-menu]");
  if (userMenu) {
    var menuTrigger = userMenu.querySelector("[data-user-menu-trigger]");
    var menuDropdown = userMenu.querySelector("[data-user-menu-dropdown]");

    if (menuTrigger && menuDropdown) {
      function closeUserMenu(returnFocus) {
        menuDropdown.hidden = true;
        menuTrigger.setAttribute("aria-expanded", "false");
        if (returnFocus) {
          menuTrigger.focus();
        }
      }

      menuTrigger.addEventListener("click", function () {
        var isOpen = menuTrigger.getAttribute("aria-expanded") === "true";
        menuTrigger.setAttribute("aria-expanded", String(!isOpen));
        menuDropdown.hidden = isOpen;
      });

      document.addEventListener("click", function (event) {
        if (!userMenu.contains(event.target)) {
          closeUserMenu(false);
        }
      });

      document.addEventListener("keydown", function (event) {
        if (
          event.key === "Escape" &&
          menuTrigger.getAttribute("aria-expanded") === "true"
        ) {
          closeUserMenu(true);
        }
      });
    }
  }

  document.querySelectorAll("[data-flash-dismiss]").forEach(function (button) {
    button.addEventListener("click", function () {
      var banner = button.closest(".flash-banner");
      if (banner) {
        banner.remove();
      }
    });
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && body.classList.contains("mobile-sidebar-open")) {
      setMobileSidebarOpen(false);
      if (sidebarToggle) {
        sidebarToggle.focus();
      }
    }
  });
})();
