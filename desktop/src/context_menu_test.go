package main

import (
	"os"
	"strings"
	"testing"
)

func TestContextMenuJSOffersOnlyTheTwoWantedEntries(t *testing.T) {
	js := contextMenuJS()
	for _, needle := range []string{
		"上一页",
		"重新加载系统",
		"history.back()",
		"location.reload()",
		"event.preventDefault()",
	} {
		if !strings.Contains(js, needle) {
			t.Fatalf("context menu JS missing %q", needle)
		}
	}
	// The whole reason the native menu is switched off.
	for _, forbidden := range []string{"save", "print", "Save", "Print", "另存", "打印"} {
		if strings.Contains(js, forbidden) {
			t.Fatalf("context menu JS must not offer %q", forbidden)
		}
	}
}

func TestContextMenuJSDoesNotNeedTheWailsRuntime(t *testing.T) {
	// It runs on the dashboard origin, which never loads /wails/runtime.js.
	if strings.Contains(contextMenuJS(), "_wails") {
		t.Fatal("context menu must work on the remote dashboard origin")
	}
}

func TestWindowsDisableTheNativeContextMenu(t *testing.T) {
	src, err := os.ReadFile("main.go")
	if err != nil {
		t.Fatal(err)
	}
	body := string(src)
	// Both the main window and the settings popover, or one of them keeps the
	// native menu with Save-as and Print.
	if got := strings.Count(body, "DefaultContextMenuDisabled: true"); got != 2 {
		t.Fatalf("DefaultContextMenuDisabled set %d times, want 2 (main + settings)", got)
	}
}
