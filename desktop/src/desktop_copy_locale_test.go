package main

import (
	"strings"
	"testing"
)

// A key missing from the Chinese table falls back to English silently, which is
// how "everything translatable is Chinese" breaks without any test going red.
func TestDesktopCopyChineseCoversEveryEnglishKey(t *testing.T) {
	english := desktopCopy[LocaleEN]
	chinese := desktopCopy[LocaleZH]
	for key := range english {
		if _, ok := chinese[key]; !ok {
			t.Errorf("no Chinese copy for %q", key)
		}
	}
	for key := range chinese {
		if _, ok := english[key]; !ok {
			t.Errorf("Chinese copy for %q has no English counterpart", key)
		}
	}
}

func TestDesktopCopyPlaceholdersMatchAcrossLocales(t *testing.T) {
	for _, key := range []string{
		copyStatusBackupDatabase, copyHealthNotReady5xx,
		copyHealthNotReadyConnect, copyHealthNotReady,
	} {
		want := strings.Count(desktopCopy[LocaleEN][key], "%s")
		got := strings.Count(desktopCopy[LocaleZH][key], "%s")
		if want != got {
			t.Errorf("%s: %d %%s in English but %d in Chinese", key, want, got)
		}
	}
	for _, key := range []string{copyWaitNMinutes, copyWaitNSeconds} {
		if strings.Count(desktopCopy[LocaleEN][key], "%d") != strings.Count(desktopCopy[LocaleZH][key], "%d") {
			t.Errorf("%s: percent-d count differs between locales", key)
		}
	}
}

func TestShellDefaultsToChinese(t *testing.T) {
	if got := defaultSettings().Locale; got != LocaleZH {
		t.Fatalf("default shell locale = %s, want %s", got, LocaleZH)
	}
}
