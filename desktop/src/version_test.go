package main

import "testing"

func TestCompareVersionsUsesLocalSegment(t *testing.T) {
	// The shipped runtime is replaced only when the bundled version compares
	// strictly greater, so build metadata must not look equal.
	if got := compareVersions("1.0.2b6+z03", "1.0.2b6+z02"); got != 1 {
		t.Fatalf("z03 vs z02: got %d", got)
	}
	if got := compareVersions("1.0.2b6+z02", "1.0.2b6+z03"); got != -1 {
		t.Fatalf("z02 vs z03: got %d", got)
	}
	if got := compareVersions("1.0.2b6+z02", "1.0.2b6+z02"); got != 0 {
		t.Fatalf("identical: got %d", got)
	}
}

func TestCompareVersionsLocalOrdering(t *testing.T) {
	cases := []struct {
		left, right string
		want        int
	}{
		{"1.0.2", "1.0.2+z01", -1},
		{"1.0.2+z01", "1.0.2", 1},
		{"1.0.2b6+z99", "1.0.2+z01", -1},
		{"1.0.2+z01", "1.0.3", -1},
		{"1.0.2+z09", "1.0.2+z10", -1},
		{"1.0.2+1", "1.0.2+a", -1},
		{"1.0.2+a.1", "1.0.2+a.2", -1},
		{"1.0.2+a", "1.0.2+a.1", -1},
		{"1.0.2+Z01", "1.0.2+z01", 0},
		{"1.0.2+a-b", "1.0.2+a.b", 0},
	}
	for _, c := range cases {
		if got := compareVersions(c.left, c.right); got != c.want {
			t.Errorf("compareVersions(%q, %q) = %d, want %d", c.left, c.right, got, c.want)
		}
	}
}

func TestCompareVersionsPaddedBuildTagsSortNumerically(t *testing.T) {
	// Unpadded tags would sort z10 below z9 as plain strings.
	sequence := []string{"1.0.2b6+z01", "1.0.2b6+z02", "1.0.2b6+z09", "1.0.2b6+z10", "1.0.2b6+z99"}
	for i := 1; i < len(sequence); i++ {
		if got := compareVersions(sequence[i-1], sequence[i]); got != -1 {
			t.Errorf("%s should sort below %s, got %d", sequence[i-1], sequence[i], got)
		}
	}
	// Alphanumeric local segments compare as strings, so an unpadded z10 sorts
	// below z9 — the reason the +zNN scheme is zero-padded.
	if got := compareVersions("1.0.2b6+z10", "1.0.2b6+z9"); got != -1 {
		t.Errorf("unpadded z10 vs z9: got %d", got)
	}
}

func TestParseVersionKeepsUnparsableLocalOutOfKey(t *testing.T) {
	// Non-PEP 440 strings fall back to the numeric key and must stay comparable.
	if got := compareVersions("0.9.32", "0.9.31"); got != 1 {
		t.Fatalf("0.9.32 vs 0.9.31: got %d", got)
	}
	if got := compareVersions("latest", "latest"); got != 0 {
		t.Fatalf("non-version strings: got %d", got)
	}
}
