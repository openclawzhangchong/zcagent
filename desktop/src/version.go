package main

import (
	"regexp"
	"strconv"
	"strings"
)

// Keep ordering aligned with octop.infra.setup.self_update.parse_version.
// Local segments (+local) decide the comparison when everything before them is
// equal: releases that differ only by build metadata, such as 1.0.2b6+z02 vs
// 1.0.2b6+z03, must not look identical, or the bundled runtime is never replaced.

var pep440RE = regexp.MustCompile(`(?i)^v?(?:(?P<epoch>\d+)!)?(?P<release>\d+(?:\.\d+)*)(?:[-_\.]?(?P<pre_l>alpha|a|beta|b|preview|pre|rc|c)[-_\.]?(?P<pre_n>\d+)?)?(?:(?:[-_\.]?(?P<post_l>post|rev|r)[-_\.]?(?P<post_n>\d+))|(?:-(?P<post_n1>\d+)))?(?:[-_\.]?(?P<dev_l>dev)[-_\.]?(?P<dev_n>\d+)?)?(?:\+(?P<local>[a-z0-9]+(?:[-_\.][a-z0-9]+)*))?$`)

var preRank = map[string]int{
	"a": 0, "alpha": 0,
	"b": 1, "beta": 1,
	"c": 2, "rc": 2, "pre": 2, "preview": 2,
}

const releasePad = 8

// localSegment is one +-separated part of a PEP 440 local version. Numeric parts
// always sort below alphanumeric parts, mirroring packaging's LocalSegment.
type localSegment struct {
	numeric bool
	value   int
	text    string
}

type versionKey struct {
	epoch   int
	release [releasePad]int
	pre     []int
	post    int
	dev     []int
	local   []localSegment
}

func compareVersions(left, right string) int {
	a := parseVersion(left)
	b := parseVersion(right)
	if a.epoch != b.epoch {
		return cmpInt(a.epoch, b.epoch)
	}
	for i := 0; i < releasePad; i++ {
		if a.release[i] != b.release[i] {
			return cmpInt(a.release[i], b.release[i])
		}
	}
	if c := compareIntSlice(a.pre, b.pre); c != 0 {
		return c
	}
	if a.post != b.post {
		return cmpInt(a.post, b.post)
	}
	if c := compareIntSlice(a.dev, b.dev); c != 0 {
		return c
	}
	return compareLocal(a.local, b.local)
}

func compareLocal(left, right []localSegment) int {
	if left == nil || right == nil {
		return cmpInt(b2i(left != nil), b2i(right != nil))
	}
	n := min(len(left), len(right))
	for i := 0; i < n; i++ {
		l, r := left[i], right[i]
		if l.numeric != r.numeric {
			return cmpInt(b2i(r.numeric), b2i(l.numeric))
		}
		if l.numeric {
			if c := cmpInt(l.value, r.value); c != 0 {
				return c
			}
			continue
		}
		if c := strings.Compare(strings.ToLower(l.text), strings.ToLower(r.text)); c != 0 {
			return c
		}
	}
	return cmpInt(len(left), len(right))
}

func b2i(v bool) int {
	if v {
		return 1
	}
	return 0
}

func parseLocal(value string) []localSegment {
	if value == "" {
		return nil
	}
	var segments []localSegment
	for _, part := range strings.FieldsFunc(value, func(r rune) bool {
		return r == '.' || r == '-' || r == '_'
	}) {
		if digitsOnly(part) {
			n, _ := strconv.Atoi(part)
			segments = append(segments, localSegment{numeric: true, value: n})
			continue
		}
		segments = append(segments, localSegment{text: part})
	}
	return segments
}

func digitsOnly(value string) bool {
	if value == "" {
		return false
	}
	for _, ch := range value {
		if ch < '0' || ch > '9' {
			return false
		}
	}
	return true
}

func parseVersion(value string) versionKey {
	value = strings.TrimSpace(value)
	match := pep440RE.FindStringSubmatch(value)
	if match == nil {
		return numericVersionKey(value)
	}
	get := subexpGetter(pep440RE, match)
	key := versionKey{}
	if epoch := get("epoch"); epoch != "" {
		key.epoch, _ = strconv.Atoi(epoch)
	}
	for i, part := range strings.Split(get("release"), ".") {
		if i >= releasePad {
			break
		}
		key.release[i], _ = strconv.Atoi(part)
	}
	preL := strings.ToLower(get("pre_l"))
	devL := get("dev_l")
	if preL != "" {
		n := 0
		if raw := get("pre_n"); raw != "" {
			n, _ = strconv.Atoi(raw)
		}
		key.pre = []int{0, preRank[preL], n}
	} else if devL != "" {
		key.pre = []int{-1}
	} else {
		key.pre = []int{1}
	}
	if raw := get("post_n"); raw != "" {
		key.post, _ = strconv.Atoi(raw)
	} else if raw := get("post_n1"); raw != "" {
		key.post, _ = strconv.Atoi(raw)
	} else {
		key.post = -1
	}
	if devL != "" {
		n := 0
		if raw := get("dev_n"); raw != "" {
			n, _ = strconv.Atoi(raw)
		}
		key.dev = []int{0, n}
	} else {
		key.dev = []int{1}
	}
	key.local = parseLocal(get("local"))
	return key
}

func numericVersionKey(value string) versionKey {
	key := versionKey{pre: []int{1}, post: -1, dev: []int{1}}
	parts := strings.Split(value, ".")
	if len(parts) == 0 {
		parts = []string{""}
	}
	for i, segment := range parts {
		if i >= releasePad {
			break
		}
		numeric := ""
		for _, ch := range segment {
			if ch < '0' || ch > '9' {
				break
			}
			numeric += string(ch)
		}
		if numeric != "" {
			key.release[i], _ = strconv.Atoi(numeric)
		}
	}
	return key
}

func subexpGetter(re *regexp.Regexp, match []string) func(string) string {
	names := re.SubexpNames()
	return func(name string) string {
		for i, n := range names {
			if n == name {
				return match[i]
			}
		}
		return ""
	}
}

func compareIntSlice(left, right []int) int {
	n := min(len(left), len(right))
	for i := 0; i < n; i++ {
		if c := cmpInt(left[i], right[i]); c != 0 {
			return c
		}
	}
	return cmpInt(len(left), len(right))
}

func cmpInt(left, right int) int {
	if left < right {
		return -1
	}
	if left > right {
		return 1
	}
	return 0
}
