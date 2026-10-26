package main

import (
	"encoding/json"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"testing"
)

type memory map[string][]byte

func (m memory) Paths() []string {
	out := []string{}
	for key := range m {
		out = append(out, key)
	}
	sort.Strings(out)
	return out
}
func (m memory) Read(file string) ([]byte, error) {
	if value, ok := m[file]; ok {
		return value, nil
	}
	return nil, os.ErrNotExist
}
func (m memory) Mode(string) string { return "100644" }
func clone(m memory) memory {
	out := memory{}
	for key, value := range m {
		out[key] = append([]byte{}, value...)
	}
	return out
}
func fixture() memory {
	inv := Inventory{Schema: 1, Controls: []string{inventoryPath, "build/control"}, Images: []Definition{
		{Image: "app", Target: "app", Dockerfile: "Dockerfile"}, {Image: "ops", Target: "ops", Dockerfile: "Dockerfile"}}}
	encoded, _ := json.Marshal(inv)
	return memory{inventoryPath: encoded, "build/control": []byte("pinned gate"), "requirements.txt": []byte("locked dependency"),
		"ui/app.js": []byte("current screen"), "unrelated.md": []byte("not copied"),
		"Dockerfile": []byte("FROM scratch AS builder\nCOPY requirements.txt /out/\nFROM scratch AS runtime\nCOPY --from=builder /out/ /out/\nFROM runtime AS app\nCOPY ui/ /ui/\nFROM runtime AS ops\nCMD [\"ops\"]\n")}
}
func planFor(t *testing.T, s Snapshot) Plan {
	t.Helper()
	value, err := buildPlan(s, strings.Repeat("a", 40))
	if err != nil {
		t.Fatal(err)
	}
	return value
}
func encoded(plan Plan) []byte { value, _ := json.Marshal(plan); return value }
func selected(selection Selection) []string {
	out := []string{}
	for _, definition := range selection.Include {
		out = append(out, definition.Image)
	}
	sort.Strings(out)
	return out
}
func assertNames(t *testing.T, got Selection, wanted ...string) {
	t.Helper()
	sort.Strings(wanted)
	if strings.Join(selected(got), ",") != strings.Join(wanted, ",") {
		t.Fatalf("selected %v, wanted %v", selected(got), wanted)
	}
}
func contains(image Image, file string) bool {
	for _, input := range image.Inputs {
		if input.Path == file {
			return true
		}
	}
	return false
}

func TestStageOwnershipAndInputChanges(t *testing.T) {
	before := fixture()
	prior := planFor(t, before)
	assertNames(t, selectImages(prior, encoded(prior), false))
	after := clone(before)
	after["ui/app.js"] = []byte("new screen")
	assertNames(t, selectImages(planFor(t, after), encoded(prior), false), "app")
	after = clone(before)
	after["requirements.txt"] = []byte("new locked dependency")
	assertNames(t, selectImages(planFor(t, after), encoded(prior), false), "app", "ops")
	after = clone(before)
	after["unrelated.md"] = []byte("changed outside image inputs")
	assertNames(t, selectImages(planFor(t, after), encoded(prior), false))
	after = clone(before)
	after["build/control"] = []byte("new gate")
	assertNames(t, selectImages(planFor(t, after), encoded(prior), false), "app", "ops")
	assertNames(t, selectImages(prior, encoded(prior), true), "app", "ops")
}
func TestRenamesDeletesAndMissingExplicitSources(t *testing.T) {
	before := fixture()
	prior := planFor(t, before)
	after := clone(before)
	after["ui/new.js"] = after["ui/app.js"]
	delete(after, "ui/app.js")
	assertNames(t, selectImages(planFor(t, after), encoded(prior), false), "app")
	after["ui/other.js"] = []byte("other")
	delete(after, "ui/new.js")
	assertNames(t, selectImages(planFor(t, after), encoded(prior), false), "app")
	delete(after, "requirements.txt")
	if _, err := buildPlan(after, strings.Repeat("a", 40)); err == nil {
		t.Fatal("missing COPY source accepted")
	}
}
func TestDockerIgnorePrecedenceNegationJSONAndDirectoryWildcards(t *testing.T) {
	source := fixture()
	source["Dockerfile"] = []byte("FROM scratch AS app\nCOPY [\"assets/*\", \"/assets/\"]\nFROM app AS ops\n")
	source[".dockerignore"] = []byte("assets/\n")
	source["Dockerfile.dockerignore"] = []byte("**\n!assets/\n!assets/**\nassets/private/**\n!assets/private/keep.txt\n**/*.pyc\n")
	source["assets/visible.txt"] = []byte("visible")
	source["assets/nested/deep.txt"] = []byte("recursive directory wildcard")
	source["assets/private/no.txt"] = []byte("ignored")
	source["assets/private/keep.txt"] = []byte("explicit negation")
	source["assets/nested/cache.pyc"] = []byte("ignored")
	image := planFor(t, source).Images[0]
	for _, file := range []string{"assets/visible.txt", "assets/nested/deep.txt", "assets/private/keep.txt", "Dockerfile.dockerignore"} {
		if !contains(image, file) {
			t.Fatalf("missing actual input %s", file)
		}
	}
	for _, file := range []string{"assets/private/no.txt", "assets/nested/cache.pyc", ".dockerignore"} {
		if contains(image, file) {
			t.Fatalf("included ignored input %s", file)
		}
	}
	before := planFor(t, source)
	source["Dockerfile.dockerignore"] = append(source["Dockerfile.dockerignore"], []byte("assets/visible.txt\n")...)
	assertNames(t, selectImages(planFor(t, source), encoded(before), false), "app", "ops")
}
func TestStageAndMountMaterials(t *testing.T) {
	source := fixture()
	pinned := "example.invalid/vendor@sha256:" + strings.Repeat("b", 64)
	source["Dockerfile"] = []byte("FROM scratch AS builder\nCOPY requirements.txt /out/\nFROM scratch AS app\nCOPY --from=0 /out/ /out/\nCOPY --from=" + pinned + " /lib /lib\nRUN --mount=type=bind,source=ui,target=/ui cat /ui/app.js\nFROM app AS ops\n")
	image := planFor(t, source).Images[0]
	if !contains(image, "requirements.txt") || !contains(image, "ui/app.js") {
		t.Fatal("stage/bind inputs omitted")
	}
	if strings.Join(image.Materials, ",") != pinned+",scratch" {
		t.Fatalf("unexpected materials %v", image.Materials)
	}
}
func TestUnsupportedOrAmbiguousInputsFailClosed(t *testing.T) {
	for _, recipe := range []string{
		"FROM alpine:latest AS app\nFROM app AS ops\n",
		"FROM scratch AS app\nARG SOURCE\nCOPY $SOURCE /out/\nFROM app AS ops\n",
		"FROM scratch AS app\nADD ui/ /out/\nFROM app AS ops\n",
		"FROM scratch AS app\nFROM scratch AS app\nFROM app AS ops\n",
		"FROM app AS app\nFROM app AS ops\n",
		"FROM scratch AS app\nCOPY --from=99 /out /out\nFROM app AS ops\n",
	} {
		source := fixture()
		source["Dockerfile"] = []byte(recipe)
		if _, err := buildPlan(source, strings.Repeat("a", 40)); err == nil {
			t.Fatalf("unsupported recipe accepted: %s", recipe)
		}
	}
	source := fixture()
	var inv Inventory
	json.Unmarshal(source[inventoryPath], &inv)
	inv.Controls = append(inv.Controls, "missing/**")
	source[inventoryPath], _ = json.Marshal(inv)
	if _, err := buildPlan(source, strings.Repeat("a", 40)); err == nil {
		t.Fatal("missing build-control path accepted")
	}
}

type symbolic struct{ memory }

func (s symbolic) Mode(file string) string {
	if file == "ui/app.js" {
		return "120000"
	}
	return "100644"
}
func TestSymlinksCannotIntroduceUnaccountedInputs(t *testing.T) {
	if _, err := buildPlan(symbolic{fixture()}, strings.Repeat("a", 40)); err == nil {
		t.Fatal("source symlink accepted")
	}
}

func TestBaselineMustBeCompleteStrictAndInternallyConsistent(t *testing.T) {
	current := planFor(t, fixture())
	for _, bad := range [][]byte{nil, []byte("{"), []byte(`{"schema":1}`), append(encoded(current), []byte(" {}")...)} {
		assertNames(t, selectImages(current, bad, false), "app", "ops")
	}
	mutations := []func(*Plan){
		func(p *Plan) { p.SourceCommit = "main" }, func(p *Plan) { p.Schema = 2 }, func(p *Plan) { p.Images = p.Images[:1] },
		func(p *Plan) { p.Images[1] = p.Images[0] }, func(p *Plan) { p.Images[0].Inputs[0].SHA256 = strings.Repeat("f", 64) },
		func(p *Plan) { p.Images[0].Inputs = nil }, func(p *Plan) { p.Images[0].Fingerprint = "missing" },
	}
	for _, change := range mutations {
		var prior Plan
		json.Unmarshal(encoded(current), &prior)
		change(&prior)
		assertNames(t, selectImages(current, encoded(prior), false), "app", "ops")
	}
	var object map[string]any
	json.Unmarshal(encoded(current), &object)
	object["unreviewed"] = true
	bad, _ := json.Marshal(object)
	assertNames(t, selectImages(current, bad, false), "app", "ops")
}

func currentWorkingSource(t *testing.T) memory {
	t.Helper()
	root, err := filepath.Abs("../..")
	if err != nil {
		t.Fatal(err)
	}
	output, err := exec.Command("git", "-C", root, "ls-files", "-z", "--cached", "--others", "--exclude-standard").Output()
	if err != nil {
		t.Fatal(err)
	}
	files := memory{}
	for _, name := range strings.Split(string(output), "\x00") {
		if name == "" {
			continue
		}
		data, err := os.ReadFile(filepath.Join(root, name))
		if errors.Is(err, os.ErrNotExist) {
			continue
		}
		if err != nil {
			t.Fatal(err)
		}
		files[name] = data
	}
	return files
}
func TestActualRepositoryRecipesAndCurrentConsumerGraph(t *testing.T) {
	source := currentWorkingSource(t)
	current := planFor(t, source)
	expected := map[string][]string{
		"docs/architecture.md":                                {"platform-guide"},
		"docs/platform/guide.ar.md":                           {"platform-guide"},
		"platform/agents/platform-guide/current-docs.json":    {"platform-guide"},
		"platform/agents/platform-guide/tools/build-index.js": {"platform-guide"},
		"platform/core/ui/core.js":                            {"agent-platform-app", "agent-financial", "platform-guide"},
		"platform/agents/financial/finance_agent/store.py":    {"agent-financial"},
		"platform/agents/financial/agent.yaml":                {"agent-platform-app"},
		"platform/core/ui/map.js":                             {"agent-platform-app"},
		"platform/core/src/agent_platform/ui_assets.py":       {"agent-platform-app", "agent-platform-ops", "agent-financial"},
		"requirements-litellm-candidate.txt":                  {},
        "requirements-gateway.txt":                            {"agent-platform-gateway"},
        "requirements-platform.txt":                           {"agent-platform-app", "agent-platform-ops"},
        "platform/core/src/agent_platform/programs/redactor_server.py": {"agent-platform-app", "agent-platform-ops", "agent-platform-redactor"},
        "platform/core/database/finance.sql":                 {"agent-platform-app"},
		"platform/clouds/gke/release-rc1.lock.json":           {}, "platform/clouds/gke/images.json": {},
		"docs/evidence/synthetic-untracked-note.md": {}, "docs/handoffs/synthetic-private.md": {},
		"platform/agents/platform-guide/node_modules/dependency.js": {},
	}
	for file, names := range expected {
		t.Run(file, func(t *testing.T) {
			after := clone(source)
			after[file] = append(after[file], []byte("\nsynthetic change")...)
			assertNames(t, selectImages(planFor(t, after), encoded(current), false), names...)
		})
	}
	for _, image := range current.Images {
		for _, input := range image.Inputs {
			if strings.Contains(input.Path, "node_modules/") || strings.HasSuffix(input.Path, ".pyc") || strings.HasPrefix(input.Path, "docs/evidence/") {
				t.Fatalf("ignored path entered %s: %s", image.Image, input.Path)
			}
		}
	}
}
func TestGitSnapshotReadsExactSourceAndRejectsUnboundReferences(t *testing.T) {
	root := t.TempDir()
	source := fixture()
	for file, data := range source {
		target := filepath.Join(root, file)
		if err := os.MkdirAll(filepath.Dir(target), 0755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(target, data, 0644); err != nil {
			t.Fatal(err)
		}
	}
	for _, args := range [][]string{{"init", "-q"}, {"add", "."}, {"-c", "user.name=Synthetic test", "-c", "user.email=test@example.invalid", "commit", "-qm", "synthetic fixture"}} {
		if _, err := git(root, args...); err != nil {
			t.Fatal(err)
		}
	}
	head, _ := git(root, "rev-parse", "HEAD")
	revision := strings.TrimSpace(string(head))
	s, err := snapshot(root, revision)
	if err != nil {
		t.Fatal(err)
	}
	before := planFor(t, s)
	os.WriteFile(filepath.Join(root, "ui/app.js"), []byte("uncommitted mutation"), 0644)
	os.WriteFile(filepath.Join(root, "ui/extra.js"), []byte("untracked injection"), 0644)
	fresh, err := snapshot(root, revision)
	if err != nil {
		t.Fatal(err)
	}
	assertNames(t, selectImages(planFor(t, fresh), encoded(before), false))
	if _, err := snapshot(root, "HEAD"); err == nil {
		t.Fatal("unbound branch accepted")
	}
}

func TestSourceArgumentMustBeDeclaredInAReachableStage(t *testing.T) {
	source := fixture()
	var inv Inventory
	json.Unmarshal(source[inventoryPath], &inv)
	inv.Images[0].SourceArgument = "SOURCE_COMMIT"
	source[inventoryPath], _ = json.Marshal(inv)
	if _, err := buildPlan(source, strings.Repeat("a", 40)); err == nil {
		t.Fatal("undeclared source argument accepted")
	}
	source["Dockerfile"] = []byte(strings.Replace(string(source["Dockerfile"]), "COPY requirements.txt", "ARG SOURCE_COMMIT\nCOPY requirements.txt", 1))
	planFor(t, source)
}
