using System.Security.Cryptography;
using System.Text.Json;

namespace Patterna;

public sealed record SimulationRuntime(
    string RootDirectory,
    string RuntimeVersion,
    string GarmentCodePythonPath,
    string Style3DPythonPath,
    string BlenderPath,
    string CompilerPath,
    string ToolsDirectory,
    string Origin,
    string AvatarBackend = "CharMorph Antonia (manifest undeclared)",
    string AvatarOutputLicense = "CC-BY 3.0 (manifest undeclared)",
    string? AvatarLicensePath = null,
    string? AvatarCharacterDirectory = null);

internal sealed record SimulationRuntimeManifest(
    string SchemaVersion,
    string RuntimeVersion,
    string GarmentCodePython,
    string Style3DPython,
    string Blender,
    string Compiler,
    string ToolsDirectory,
    Dictionary<string, string> EntrypointSha256,
    string? AvatarBackend = null,
    string? AvatarOutputLicense = null,
    string? AvatarLicenseFile = null,
    string? AvatarCharacterDirectory = null);

public static class SimulationRuntimeLocator
{
    public const string ManifestSchema = "patterna.simulation-runtime/1.0";
    public const string InstalledRuntimeDirectoryName = "SimulationRuntime";
    public const string CurrentRuntimeDirectoryName = "current";
    public const string ManifestFileName = "runtime-manifest.json";

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase
    };

    private static readonly string[] RequiredScripts =
    [
        "fit_charmorph_profile.py",
        "generate_charmorph_avatar.py",
        "prepare_charmorph_garmentcode_body.py",
        "charmorph_collision.py",
        "charmorph_character.py",
        "charmorph_anatomy.py",
        "charmorph_glb.py",
        "verify_charmorph_glb.py",
        "charmorph_morphs.py",
        "charmorph_profile_controls.py",
        "mesh_torso_arcs.py",
        "generate_body_profile_from_mesh.py",
        "export_garmentcode_pattern_mesh.py",
        "build_style3d_source.py",
        "prefit_newton_style3d.py",
        "patterna_style3d_sewing.py",
        "render_product_acceptance.py",
        "record_product_visual_review.py",
        "product_registration.py"
    ];

    public static SimulationRuntime Resolve(
        string applicationBaseDirectory,
        string localAppDataPath)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(applicationBaseDirectory);
        ArgumentException.ThrowIfNullOrWhiteSpace(localAppDataPath);

        string installedManifest = Path.Combine(
            localAppDataPath,
            InstalledRuntimeDirectoryName,
            CurrentRuntimeDirectoryName,
            ManifestFileName);
        string bundledManifest = Path.Combine(
            applicationBaseDirectory,
            InstalledRuntimeDirectoryName,
            ManifestFileName);
        List<string> rejectedManifests = [];
        foreach (string manifestPath in new[] { installedManifest, bundledManifest }.Distinct(StringComparer.OrdinalIgnoreCase))
        {
            if (!File.Exists(manifestPath))
            {
                continue;
            }
            if (TryLoadManifest(manifestPath, out SimulationRuntime? runtime, out string rejection))
            {
                return runtime!;
            }
            rejectedManifests.Add($"{manifestPath}: {rejection}");
        }

        if (TryCreateDeveloperRuntime(
                applicationBaseDirectory,
                localAppDataPath,
                out SimulationRuntime? developerRuntime))
        {
            return developerRuntime!;
        }

        string manifestDetail = rejectedManifests.Count == 0
            ? "No installed runtime manifest was found."
            : string.Join(" ", rejectedManifests);
        throw new SimulationPipelineException(
            $"Patternal's simulation runtime is unavailable. {manifestDetail} " +
            "Install or repair the Patternal simulation runtime before running cloth simulation.");
    }

    public static bool TryLoadManifest(
        string manifestPath,
        out SimulationRuntime? runtime,
        out string rejection)
    {
        runtime = null;
        rejection = string.Empty;
        try
        {
            string fullManifestPath = Path.GetFullPath(manifestPath);
            string runtimeRoot = Path.GetDirectoryName(fullManifestPath)!;
            SimulationRuntimeManifest? manifest = JsonSerializer.Deserialize<SimulationRuntimeManifest>(
                File.ReadAllText(fullManifestPath),
                JsonOptions);
            if (manifest is null ||
                !string.Equals(manifest.SchemaVersion, ManifestSchema, StringComparison.Ordinal) ||
                string.IsNullOrWhiteSpace(manifest.RuntimeVersion))
            {
                rejection = $"The manifest must use {ManifestSchema} and declare a runtime version.";
                return false;
            }
            bool declaresAnyAvatarMetadata =
                !string.IsNullOrWhiteSpace(manifest.AvatarBackend) ||
                !string.IsNullOrWhiteSpace(manifest.AvatarOutputLicense) ||
                !string.IsNullOrWhiteSpace(manifest.AvatarLicenseFile) ||
                !string.IsNullOrWhiteSpace(manifest.AvatarCharacterDirectory);
            bool declaresCompleteAvatarMetadata =
                !string.IsNullOrWhiteSpace(manifest.AvatarBackend) &&
                !string.IsNullOrWhiteSpace(manifest.AvatarOutputLicense) &&
                !string.IsNullOrWhiteSpace(manifest.AvatarLicenseFile) &&
                !string.IsNullOrWhiteSpace(manifest.AvatarCharacterDirectory);
            if (declaresAnyAvatarMetadata && !declaresCompleteAvatarMetadata)
            {
                rejection = "Avatar runtime metadata must declare backend, output license, license file, and character directory together.";
                return false;
            }

            string garmentCodePython = ResolveContainedPath(runtimeRoot, manifest.GarmentCodePython, false);
            string style3DPython = ResolveContainedPath(runtimeRoot, manifest.Style3DPython, false);
            string blender = ResolveContainedPath(runtimeRoot, manifest.Blender, false);
            string compiler = ResolveContainedPath(runtimeRoot, manifest.Compiler, false);
            string toolsDirectory = ResolveContainedPath(runtimeRoot, manifest.ToolsDirectory, true);
            string? avatarLicensePath = string.IsNullOrWhiteSpace(manifest.AvatarLicenseFile)
                ? null
                : ResolveContainedPath(runtimeRoot, manifest.AvatarLicenseFile, false);
            string? avatarCharacterDirectory = string.IsNullOrWhiteSpace(manifest.AvatarCharacterDirectory)
                ? null
                : ResolveContainedPath(runtimeRoot, manifest.AvatarCharacterDirectory, true);
            string[] requiredFiles =
            [
                garmentCodePython,
                style3DPython,
                blender,
                compiler,
                .. RequiredScripts.Select(script => Path.Combine(toolsDirectory, script)),
                .. (avatarLicensePath is null ? Array.Empty<string>() : new[] { avatarLicensePath })
            ];
            string? missing = requiredFiles.FirstOrDefault(path => !File.Exists(path));
            if (missing is not null)
            {
                rejection = $"Required runtime entry point is missing: {missing}";
                return false;
            }

            Dictionary<string, string> hashes = new(StringComparer.OrdinalIgnoreCase);
            foreach ((string relativePath, string hash) in manifest.EntrypointSha256 ?? [])
            {
                string normalizedPath = NormalizeRelativePath(relativePath);
                if (!hashes.TryAdd(normalizedPath, hash))
                {
                    rejection = $"Runtime manifest repeats an integrity path: {normalizedPath}";
                    return false;
                }
            }
            foreach (string requiredFile in requiredFiles)
            {
                string relativePath = NormalizeRelativePath(Path.GetRelativePath(runtimeRoot, requiredFile));
                if (!hashes.TryGetValue(relativePath, out string? expectedHash) ||
                    !IsSha256(expectedHash) ||
                    !string.Equals(FileSha256(requiredFile), expectedHash, StringComparison.OrdinalIgnoreCase))
                {
                    rejection = $"Runtime entry point failed its SHA-256 check: {relativePath}";
                    return false;
                }
            }
            foreach ((string relativePath, string expectedHash) in hashes)
            {
                string integrityFile = ResolveContainedPath(runtimeRoot, relativePath, false);
                if (!File.Exists(integrityFile) ||
                    !IsSha256(expectedHash) ||
                    !string.Equals(FileSha256(integrityFile), expectedHash, StringComparison.OrdinalIgnoreCase))
                {
                    rejection = $"Runtime integrity file failed its SHA-256 check: {relativePath}";
                    return false;
                }
            }

            runtime = new SimulationRuntime(
                runtimeRoot,
                manifest.RuntimeVersion,
                garmentCodePython,
                style3DPython,
                blender,
                compiler,
                toolsDirectory,
                "installed-manifest",
                string.IsNullOrWhiteSpace(manifest.AvatarBackend)
                    ? "CharMorph Antonia (manifest undeclared)"
                    : manifest.AvatarBackend,
                string.IsNullOrWhiteSpace(manifest.AvatarOutputLicense)
                    ? "CC-BY 3.0 (manifest undeclared)"
                    : manifest.AvatarOutputLicense,
                avatarLicensePath,
                avatarCharacterDirectory);
            return true;
        }
        catch (Exception exception) when (
            exception is IOException or
            UnauthorizedAccessException or
            JsonException or
            ArgumentException or
            NotSupportedException)
        {
            rejection = exception.Message;
            return false;
        }
    }

    private static bool TryCreateDeveloperRuntime(
        string applicationBaseDirectory,
        string localAppDataPath,
        out SimulationRuntime? runtime)
    {
        runtime = null;
        DirectoryInfo? directory = new(Path.GetFullPath(applicationBaseDirectory));
        for (int depth = 0; directory is not null && depth < 12; depth++, directory = directory.Parent)
        {
            string root = directory.FullName;
            if (!Directory.Exists(Path.Combine(root, "tools")) ||
                !File.Exists(Path.Combine(root, "Patternal", "Patternal.csproj")))
            {
                continue;
            }

            string garmentCodePython = Path.Combine(root, ".venv-garmentcode", "Scripts", "python.exe");
            string style3DPython = Path.Combine(root, ".venv-newton", "Scripts", "python.exe");
            string toolsDirectory = Path.Combine(root, "tools");
            string avatarCharacterDirectory = Path.Combine(root, "third_party", "CharMorph-db", "characters", "antonia");
            string? compiler = FindCurrentCompiler(root);
            string? blender = FindManagedBlender(root, localAppDataPath);
            string[] required =
            [
                garmentCodePython,
                style3DPython,
                compiler ?? string.Empty,
                blender ?? string.Empty,
                Path.Combine(avatarCharacterDirectory, "char.blend"),
                Path.Combine(avatarCharacterDirectory, "license.txt"),
                .. RequiredScripts.Select(script => Path.Combine(toolsDirectory, script))
            ];
            if (required.Any(path => string.IsNullOrWhiteSpace(path) || !File.Exists(path)))
            {
                return false;
            }

            runtime = new SimulationRuntime(
                root,
                "developer-checkout",
                garmentCodePython,
                style3DPython,
                blender!,
                compiler!,
                toolsDirectory,
                "developer-checkout",
                "CharMorph Antonia",
                "CC-BY 3.0",
                Path.Combine(avatarCharacterDirectory, "license.txt"),
                avatarCharacterDirectory);
            return true;
        }
        return false;
    }

    private static string ResolveContainedPath(string root, string relativePath, bool requireDirectory)
    {
        if (string.IsNullOrWhiteSpace(relativePath) || Path.IsPathRooted(relativePath))
        {
            throw new ArgumentException("Runtime paths must be non-empty and relative to the manifest directory.");
        }
        string fullRoot = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        string fullPath = Path.GetFullPath(Path.Combine(fullRoot, relativePath));
        if (!fullPath.StartsWith(fullRoot, StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException($"Runtime path escapes the manifest directory: {relativePath}");
        }
        if (requireDirectory && !Directory.Exists(fullPath))
        {
            throw new DirectoryNotFoundException($"Runtime directory is missing: {fullPath}");
        }
        return fullPath;
    }

    private static string? FindCurrentCompiler(string root)
    {
        string[] candidates =
        [
            Path.Combine(root, "Patternal.UnrealGarmentCompiler", "bin", "x64", "Debug", "net10.0", "Patternal.UnrealGarmentCompiler.exe"),
            Path.Combine(root, "Patternal.UnrealGarmentCompiler", "bin", "x64", "Release", "net10.0", "Patternal.UnrealGarmentCompiler.exe"),
            Path.Combine(root, "Patternal.UnrealGarmentCompiler", "bin", "Debug", "net10.0", "Patternal.UnrealGarmentCompiler.exe"),
            Path.Combine(root, "Patternal.UnrealGarmentCompiler", "bin", "Release", "net10.0", "Patternal.UnrealGarmentCompiler.exe")
        ];
        return candidates
            .Where(File.Exists)
            .OrderByDescending(CompilerBuildTimestampUtc)
            .FirstOrDefault();
    }

    private static DateTime CompilerBuildTimestampUtc(string executablePath)
    {
        string assemblyPath = Path.ChangeExtension(executablePath, ".dll");
        return File.Exists(assemblyPath)
            ? File.GetLastWriteTimeUtc(assemblyPath)
            : File.GetLastWriteTimeUtc(executablePath);
    }

    private static string? FindManagedBlender(string developerRoot, string localAppDataPath)
    {
        string[] managedRoots =
        [
            Path.Combine(localAppDataPath, "Tools"),
            Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Patternal",
                "Tools"),
            Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Patterna",
                "Tools")
        ];
        string? managed = managedRoots
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Where(Directory.Exists)
            .SelectMany(root => Directory.EnumerateFiles(root, "blender.exe", SearchOption.AllDirectories))
            .OrderByDescending(File.GetLastWriteTimeUtc)
            .FirstOrDefault();
        if (managed is not null)
        {
            return managed;
        }

        string projectRuntime = Path.Combine(developerRoot, ".runtime", "blender");
        return Directory.Exists(projectRuntime)
            ? Directory.EnumerateFiles(projectRuntime, "blender.exe", SearchOption.AllDirectories)
                .OrderByDescending(File.GetLastWriteTimeUtc)
                .FirstOrDefault()
            : null;
    }

    private static string NormalizeRelativePath(string path)
        => path.Replace(Path.DirectorySeparatorChar, '/').Replace(Path.AltDirectorySeparatorChar, '/');

    private static bool IsSha256(string? value)
        => value is { Length: 64 } && value.All(character =>
            character is >= '0' and <= '9' or >= 'a' and <= 'f' or >= 'A' and <= 'F');

    private static string FileSha256(string path)
    {
        using FileStream stream = File.OpenRead(path);
        return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
    }
}
