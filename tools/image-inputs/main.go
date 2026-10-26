// image-inputs derives build ownership using Docker's parser and ignore matcher.
// Production input is an immutable Git snapshot, never an untracked working-tree overlay.
package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"

	"github.com/moby/buildkit/frontend/dockerfile/instructions"
	"github.com/moby/buildkit/frontend/dockerfile/parser"
	"github.com/moby/patternmatcher"
	"github.com/moby/patternmatcher/ignorefile"
)

const inventoryPath = "platform/image-targets.json"

var sourceRE = regexp.MustCompile(`^[0-9a-f]{40}$`)
var digestRE = regexp.MustCompile(`^[0-9a-f]{64}$`)
var nameRE = regexp.MustCompile(`^[a-z][a-z0-9-]*$`)
var argumentRE = regexp.MustCompile(`^[A-Z][A-Z0-9_]*$`)

type Definition struct {
	Image          string `json:"image"`
	Target         string `json:"target"`
	Dockerfile     string `json:"dockerfile"`
	SourceArgument string `json:"source_argument"`
}
type Inventory struct {
	Schema   int          `json:"schema"`
	Controls []string     `json:"controls"`
	Images   []Definition `json:"images"`
}
type Input struct {
	Path   string `json:"path"`
	Mode   string `json:"mode"`
	SHA256 string `json:"sha256"`
}
type Image struct {
	Definition
	Fingerprint string   `json:"fingerprint"`
	Inputs      []Input  `json:"inputs"`
	Materials   []string `json:"materials"`
}
type Plan struct {
	Schema       int     `json:"schema"`
	SourceCommit string  `json:"source_commit"`
	Images       []Image `json:"images"`
}
type Selection struct {
	Include []Definition `json:"include"`
}

// Tests can supply explicitly synthetic snapshots; the CLI only constructs a validated Git snapshot.
type Snapshot interface {
	Paths() []string
	Read(string) ([]byte, error)
	Mode(string) string
}
type gitSnapshot struct {
	root, revision string
	paths          []string
	modes          map[string]string
	cache          map[string][]byte
}

func git(root string, args ...string) ([]byte, error) {
	command := exec.Command("git", append([]string{"-C", root}, args...)...)
	output, err := command.CombinedOutput()
	if err != nil {
		return nil, fmt.Errorf("git %s failed: %w", args[0], err)
	}
	return output, nil
}
func snapshot(root, revision string) (*gitSnapshot, error) {
	if !sourceRE.MatchString(revision) {
		return nil, errors.New("full source commit required")
	}
	actual, err := git(root, "rev-parse", revision+"^{commit}")
	if err != nil || strings.TrimSpace(string(actual)) != revision {
		return nil, errors.New("source commit unavailable")
	}
	output, err := git(root, "ls-tree", "-r", "-z", revision)
	if err != nil {
		return nil, err
	}
	s := &gitSnapshot{root: root, revision: revision, modes: map[string]string{}, cache: map[string][]byte{}}
	for _, entry := range bytes.Split(output, []byte{0}) {
		if len(entry) == 0 {
			continue
		}
		halves := bytes.SplitN(entry, []byte{'\t'}, 2)
		if len(halves) != 2 {
			return nil, errors.New("invalid Git tree")
		}
		fields := strings.Fields(string(halves[0]))
		file := string(halves[1])
		if len(fields) != 3 || fields[1] != "blob" || !safePath(file) {
			return nil, fmt.Errorf("unsupported Git input %q", file)
		}
		s.paths = append(s.paths, file)
		s.modes[file] = fields[0]
	}
	sort.Strings(s.paths)
	return s, nil
}
func (s *gitSnapshot) Paths() []string         { return s.paths }
func (s *gitSnapshot) Mode(file string) string { return s.modes[file] }
func (s *gitSnapshot) Read(file string) ([]byte, error) {
	if s.modes[file] == "" {
		return nil, os.ErrNotExist
	}
	if value, ok := s.cache[file]; ok {
		return value, nil
	}
	value, err := git(s.root, "show", s.revision+":"+file)
	if err == nil {
		s.cache[file] = value
	}
	return value, err
}
func safePath(value string) bool {
	return value != "" && value != "." && path.Clean(value) == value && !strings.HasPrefix(value, "/") && value != ".." && !strings.HasPrefix(value, "../") && !strings.ContainsAny(value, "\x00\r\n\\")
}
func decode(data []byte, value any) error {
	if len(data) > 8<<20 {
		return errors.New("JSON too large")
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(value); err != nil {
		return err
	}
	var extra any
	if decoder.Decode(&extra) != io.EOF {
		return errors.New("extra JSON data")
	}
	return nil
}
func loadInventory(s Snapshot) (Inventory, error) {
	var inv Inventory
	raw, err := s.Read(inventoryPath)
	if err != nil {
		return inv, err
	}
	if err = decode(raw, &inv); err != nil {
		return inv, err
	}
	if inv.Schema != 1 || len(inv.Images) == 0 || len(inv.Controls) == 0 {
		return inv, errors.New("invalid build inventory")
	}
	names := map[string]bool{}
	for _, d := range inv.Images {
		if !nameRE.MatchString(d.Image) || !nameRE.MatchString(d.Target) || !safePath(d.Dockerfile) || names[d.Image] || (d.SourceArgument != "" && !argumentRE.MatchString(d.SourceArgument)) {
			return inv, errors.New("invalid or duplicate image definition")
		}
		names[d.Image] = true
	}
	for _, control := range inv.Controls {
		if !safePath(control) {
			return inv, errors.New("invalid control path")
		}
	}
	return inv, nil
}

type sources struct {
	patterns []string
}
type recipe struct {
	copies    []sources
	materials []string
}

func parseRecipe(data []byte, target, sourceArgument string) (recipe, error) {
	var result recipe
	tree, err := parser.Parse(bytes.NewReader(data))
	if err != nil {
		return result, err
	}
	stages, metaArgs, err := instructions.Parse(tree.AST, nil)
	if err != nil {
		return result, err
	}
	declared := false
	for _, arg := range metaArgs {
		for _, value := range arg.Args {
			if value.Key == sourceArgument {
				declared = true
			}
		}
	}
	names := map[string]int{}
	for i, stage := range stages {
		if stage.Name != "" {
			key := strings.ToLower(stage.Name)
			if _, exists := names[key]; exists {
				return result, errors.New("duplicate stage name")
			}
			names[key] = i
		}
	}
	index, ok := names[strings.ToLower(target)]
	if !ok {
		return result, errors.New("target stage not declared")
	}
	seen := map[int]bool{}
	visiting := map[int]bool{}
	var visit func(int) error
	var from func(string) error
	from = func(reference string) error {
		if strings.Contains(reference, "$") {
			return errors.New("dynamic stage/source reference is unsupported")
		}
		if i, ok := names[strings.ToLower(reference)]; ok {
			return visit(i)
		}
		if i, err := strconv.Atoi(reference); err == nil {
			if i < 0 || i >= len(stages) {
				return errors.New("invalid stage index")
			}
			return visit(i)
		}
		if reference != "scratch" && !regexp.MustCompile(`@sha256:[0-9a-f]{64}$`).MatchString(reference) {
			return fmt.Errorf("unpinned external image %q", reference)
		}
		result.materials = append(result.materials, reference)
		return nil
	}
	visit = func(i int) error {
		if visiting[i] {
			return errors.New("stage dependency cycle")
		}
		if seen[i] {
			return nil
		}
		visiting[i] = true
		if err := from(stages[i].BaseName); err != nil {
			return err
		}
		for _, command := range stages[i].Commands {
			switch c := command.(type) {
			case *instructions.ArgCommand:
				for _, value := range c.Args {
					if value.Key == sourceArgument {
						declared = true
					}
				}
			case *instructions.CopyCommand:
				if len(c.ExcludePatterns) > 0 {
					return errors.New("COPY --exclude requires source-relative matcher support")
				}
				if c.From != "" {
					if err := from(c.From); err != nil {
						return err
					}
					continue
				}
				for _, source := range c.SourcePaths {
					if strings.Contains(source, "$") {
						return errors.New("dynamic COPY source is unsupported")
					}
				}
				result.copies = append(result.copies, sources{patterns: c.SourcePaths})
			case *instructions.AddCommand:
				return errors.New("ADD is not supported by the input contract; use explicit COPY/materials")
			case *instructions.RunCommand:
				for _, mount := range instructions.GetMounts(c) {
					if mount.Type != "bind" {
						continue
					}
					if mount.From != "" {
						if err := from(mount.From); err != nil {
							return err
						}
						continue
					}
					source := mount.Source
					if source == "" {
						source = "."
					}
					if strings.Contains(source, "$") {
						return errors.New("dynamic context mount is unsupported")
					}
					result.copies = append(result.copies, sources{patterns: []string{source}})
				}
			case *instructions.OnbuildCommand:
				return errors.New("ONBUILD is not supported by the input contract")
			}
		}
		visiting[i] = false
		seen[i] = true
		return nil
	}
	err = visit(index)
	if err == nil && sourceArgument != "" && !declared {
		err = errors.New("source argument is not declared in reachable stages")
	}
	sort.Strings(result.materials)
	result.materials = unique(result.materials)
	return result, err
}
func unique(values []string) []string {
	out := []string{}
	for _, value := range values {
		if len(out) == 0 || out[len(out)-1] != value {
			out = append(out, value)
		}
	}
	return out
}
func matcher(patterns []string) (*patternmatcher.PatternMatcher, error) {
	return patternmatcher.New(patterns)
}
func ignored(m *patternmatcher.PatternMatcher, file string) (bool, error) {
	return m.MatchesOrParentMatches(file)
}

// COPY uses Go filepath.Match, including directory matches whose descendants are copied.
func copied(pattern, file string) (bool, error) {
	pattern = strings.TrimPrefix(path.Clean("/"+pattern), "/")
	if pattern == "" || pattern == "." {
		return true, nil
	}
	for candidate := file; candidate != "."; candidate = path.Dir(candidate) {
		match, err := filepath.Match(pattern, candidate)
		if err != nil {
			return false, err
		}
		if match {
			return true, nil
		}
	}
	return false, nil
}
func hash(data []byte) string { sum := sha256.Sum256(data); return hex.EncodeToString(sum[:]) }
func imageGraph(s Snapshot, inv Inventory, d Definition) (Image, error) {
	image := Image{Definition: d, Inputs: []Input{}, Materials: []string{}}
	raw, err := s.Read(d.Dockerfile)
	if err != nil {
		return image, err
	}
	parsed, err := parseRecipe(raw, d.Target, d.SourceArgument)
	if err != nil {
		return image, fmt.Errorf("%s: %w", d.Image, err)
	}
	image.Materials = parsed.materials
	ignorePath := d.Dockerfile + ".dockerignore"
	ignoreRaw, err := s.Read(ignorePath)
	if errors.Is(err, os.ErrNotExist) {
		ignorePath = ".dockerignore"
		ignoreRaw, err = s.Read(ignorePath)
	}
	if errors.Is(err, os.ErrNotExist) {
		ignorePath = ""
		ignoreRaw = nil
	} else if err != nil {
		return image, err
	}
	patterns, err := ignorefile.ReadAll(bytes.NewReader(ignoreRaw))
	if err != nil {
		return image, err
	}
	excludes, err := matcher(patterns)
	if err != nil {
		return image, err
	}
	controls, err := matcher(inv.Controls)
	if err != nil {
		return image, err
	}
	included := map[string]bool{d.Dockerfile: true, inventoryPath: true}
	if ignorePath != "" {
		included[ignorePath] = true
	}
	for _, control := range inv.Controls {
		single, err := matcher([]string{control})
		if err != nil {
			return image, err
		}
		found := false
		for _, file := range s.Paths() {
			match, err := ignored(single, file)
			if err != nil {
				return image, err
			}
			if match {
				found = true
			}
		}
		if !found {
			return image, fmt.Errorf("build control %q matches no source", control)
		}
	}
	for _, file := range s.Paths() {
		matches, err := ignored(controls, file)
		if err != nil {
			return image, err
		}
		if matches {
			included[file] = true
		}
	}
	for _, copy := range parsed.copies {
		for _, pattern := range copy.patterns {
			found := false
			for _, file := range s.Paths() {
				match, err := copied(pattern, file)
				if err != nil {
					return image, err
				}
				if !match {
					continue
				}
				skip, err := ignored(excludes, file)
				if err != nil {
					return image, err
				}
				if skip {
					continue
				}
				if s.Mode(file) == "120000" {
					return image, fmt.Errorf("symlink input %s requires an explicit supported source contract", file)
				}
				included[file] = true
				found = true
			}
			if !found {
				return image, fmt.Errorf("%s: COPY/context input %q matches no available file", d.Image, pattern)
			}
		}
	}
	paths := []string{}
	for file := range included {
		paths = append(paths, file)
	}
	sort.Strings(paths)
	for _, file := range paths {
		if s.Mode(file) != "100644" && s.Mode(file) != "100755" {
			return image, fmt.Errorf("unsupported input mode for %s", file)
		}
		value, err := s.Read(file)
		if err != nil {
			return image, err
		}
		image.Inputs = append(image.Inputs, Input{Path: file, Mode: s.Mode(file), SHA256: hash(value)})
	}
	image.Fingerprint = contentFingerprint(image)
	return image, nil
}
func contentFingerprint(image Image) string {
	canonical, _ := json.Marshal(struct {
		Definition Definition
		Inputs     []Input
		Materials  []string
	}{image.Definition, image.Inputs, image.Materials})
	return hash(canonical)
}
func buildPlan(s Snapshot, source string) (Plan, error) {
	plan := Plan{Schema: 1, SourceCommit: source, Images: []Image{}}
	inv, err := loadInventory(s)
	if err != nil {
		return plan, err
	}
	for _, definition := range inv.Images {
		image, err := imageGraph(s, inv, definition)
		if err != nil {
			return plan, err
		}
		plan.Images = append(plan.Images, image)
	}
	return plan, nil
}
func baseline(data []byte, current Plan) (map[string]string, error) {
	var prior Plan
	if err := decode(data, &prior); err != nil {
		return nil, err
	}
	if prior.Schema != 1 || !sourceRE.MatchString(prior.SourceCommit) || len(prior.Images) != len(current.Images) {
		return nil, errors.New("invalid baseline")
	}
	wanted := map[string]bool{}
	for _, image := range current.Images {
		wanted[image.Image] = true
	}
	values := map[string]string{}
	for _, image := range prior.Images {
		if !wanted[image.Image] || values[image.Image] != "" || !digestRE.MatchString(image.Fingerprint) || len(image.Inputs) == 0 || image.Materials == nil {
			return nil, errors.New("incomplete baseline")
		}
		previous := ""
		for _, input := range image.Inputs {
			if !safePath(input.Path) || input.Path <= previous || !digestRE.MatchString(input.SHA256) || (input.Mode != "100644" && input.Mode != "100755") {
				return nil, errors.New("invalid baseline input")
			}
			previous = input.Path
		}
		if image.Fingerprint != contentFingerprint(image) {
			return nil, errors.New("baseline fingerprint mismatch")
		}
		values[image.Image] = image.Fingerprint
	}
	return values, nil
}
func selectImages(plan Plan, prior []byte, force bool) Selection {
	result := Selection{Include: []Definition{}}
	previous, err := baseline(prior, plan)
	for _, image := range plan.Images {
		if force || err != nil || previous[image.Image] != image.Fingerprint {
			result.Include = append(result.Include, image.Definition)
		}
	}
	return result
}
func run() error {
	root := flag.String("root", ".", "repository path")
	revision := flag.String("revision", "", "exact validated source commit")
	prior := flag.String("baseline", "", "trusted successful workflow input-plan artifact")
	output := flag.String("out", "", "output input plan")
	force := flag.Bool("force", false, "build every target")
	flag.Parse()
	if *output == "" || flag.NArg() != 0 {
		return errors.New("--out and --revision are required")
	}
	s, err := snapshot(*root, *revision)
	if err != nil {
		return err
	}
	plan, err := buildPlan(s, *revision)
	if err != nil {
		return err
	}
	data, err := json.MarshalIndent(plan, "", "  ")
	if err != nil {
		return err
	}
	if err = os.WriteFile(*output, append(data, '\n'), 0644); err != nil {
		return err
	}
	var previous []byte
	if *prior != "" {
		previous, err = os.ReadFile(*prior)
		if err != nil && !errors.Is(err, os.ErrNotExist) {
			return err
		}
	}
	return json.NewEncoder(os.Stdout).Encode(selectImages(plan, previous, *force))
}
func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
