package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestBundledNodeDir(t *testing.T) {
	root := t.TempDir()
	if got := bundledNodeDir(root); got != "" {
		t.Fatalf("a root without node/ must report none, got %q", got)
	}

	wrongLayout(t, root)
	if got := bundledNodeDir(root); got != "" {
		t.Fatalf("only the other platform's layout exists, got %q", got)
	}

	want := rightLayout(t, root)
	if got := bundledNodeDir(root); got != want {
		t.Fatalf("bundledNodeDir() = %q, want %q", got, want)
	}
}

// rightLayout writes the layout this OS's launcher would produce and returns the
// directory that must be prepended to PATH.
func rightLayout(t *testing.T, root string) string {
	t.Helper()
	if runtime.GOOS == "windows" {
		dir := filepath.Join(root, "node")
		writeFile(t, filepath.Join(dir, "node.exe"))
		return dir
	}
	dir := filepath.Join(root, "node", "bin")
	writeFile(t, filepath.Join(dir, "node"))
	return dir
}

// wrongLayout writes the *other* platform's layout, which must not be picked up:
// a stray node.exe in a unix package (or a bin/ dir on Windows) would put a
// directory without a working npm shim in front of PATH.
func wrongLayout(t *testing.T, root string) string {
	t.Helper()
	if runtime.GOOS == "windows" {
		dir := filepath.Join(root, "node", "bin")
		writeFile(t, filepath.Join(dir, "node"))
		return dir
	}
	dir := filepath.Join(root, "node")
	writeFile(t, filepath.Join(dir, "node.exe"))
	return dir
}

func TestMustEnvInheritedKeysReachTheChild(t *testing.T) {
	inherited := os.Getenv("PATH")
	if inherited == "" {
		t.Skip("no PATH in this environment")
	}
	// On Windows the inherited key is spelled ``Path``; the extra map appends
	// ``PATH``. If Go's env-block dedup were case-sensitive the child would keep
	// the inherited value and the bundled node would never be found.
	marker := filepath.Join(t.TempDir(), "bundled-node")
	cmd := exec.Command("cmd", "/c", "echo %PATH%")
	if runtime.GOOS != "windows" {
		cmd = exec.Command("sh", "-c", "echo $PATH")
	}
	mustEnv(cmd, map[string]string{
		"PATH": marker + string(os.PathListSeparator) + inherited,
	})
	out, err := cmd.Output()
	if err != nil {
		t.Skipf("no shell available to probe the child environment: %v", err)
	}
	got := strings.TrimSpace(strings.TrimSuffix(strings.TrimRight(string(out), "\r\n"), "%"))
	if !strings.HasPrefix(strings.ToLower(got), strings.ToLower(marker)) {
		t.Fatalf("child PATH = %q, want it to start with %q", got, marker)
	}
}

func writeFile(t *testing.T, path string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, nil, 0o644); err != nil {
		t.Fatal(err)
	}
}
