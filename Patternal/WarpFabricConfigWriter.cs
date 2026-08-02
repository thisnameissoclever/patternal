using System.Globalization;
using System.Text;

namespace Patterna;

public static class WarpFabricConfigWriter
{
    public static async Task WriteAsync(
        string path,
        FabricPhysicsDocument fabric,
        double meshResolutionCm,
        CancellationToken cancellationToken)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(path);
        string? parent = Path.GetDirectoryName(Path.GetFullPath(path));
        if (!string.IsNullOrWhiteSpace(parent))
        {
            Directory.CreateDirectory(parent);
        }
        await File.WriteAllTextAsync(
            path,
            Create(fabric, meshResolutionCm),
            new UTF8Encoding(false),
            cancellationToken);
    }

    public static string Create(FabricPhysicsDocument fabric, double meshResolutionCm)
    {
        ArgumentNullException.ThrowIfNull(fabric);
        if (!double.IsFinite(meshResolutionCm) || meshResolutionCm <= 0)
        {
            throw new ArgumentOutOfRangeException(
                nameof(meshResolutionCm),
                meshResolutionCm,
                "Mesh resolution must be a finite positive value in centimeters.");
        }
        static string Number(double value) => value.ToString("0.########", CultureInfo.InvariantCulture);

        double thicknessCm = Math.Clamp(fabric.ThicknessMillimeters / 10.0, 0.005, 0.10);
        double densityScale = Math.Clamp(fabric.MassGramsPerSquareMeter / 120.0, 0.20, 4.0);
        double bendStiffness = Math.Clamp(fabric.BendResistance / 38.0, 0.10, 8.0);
        double triangleStiffness = Math.Clamp(
            10000.0 * 9.0 / Math.Max(fabric.WeftStretchPercent, 0.5),
            2500.0,
            50000.0);
        double areaStiffness = Math.Clamp(
            10000.0 * 4.95 / Math.Max(fabric.WarpStretchPercent, 0.5),
            2500.0,
            50000.0);

        return $$"""
            sim:
              config:
                max_sim_steps: 650
                max_frame_time: null
                max_sim_time: 300
                static_threshold: 0.03
                non_static_percent: 1.5
                max_body_collisions: 0
                max_self_collisions: 0
                max_edge_strain_ratio: 0.40
                max_ninety_fifth_percentile_edge_strain_ratio: 0.15
                max_ninety_ninth_point_ninth_percentile_edge_strain_ratio: 0.29
                sim_substeps: 10
                solver_iterations: 4
                zero_gravity_steps: 10
                resolution_scale: {{Number(meshResolutionCm)}}
                ground: false
                material:
                  garment_tri_ka: {{Number(areaStiffness)}}
                  garment_edge_ke: {{Number(bendStiffness)}}
                  garment_tri_ke: {{Number(triangleStiffness)}}
                  spring_ke: 50000.0
                  sewing_ke: 50000000.0
                  garment_edge_kd: 10.0
                  garment_tri_kd: 1.0
                  spring_kd: 10.0
                  sewing_kd: 100.0
                  fabric_density: {{Number(densityScale)}}
                  fabric_thickness: {{Number(thicknessCm)}}
                  fabric_friction: {{Number(Math.Clamp(fabric.DynamicFriction, 0.05, 1.0))}}
                options:
                  enable_particle_particle_collisions: false
                  enable_triangle_particle_collisions: true
                  enable_edge_edge_collisions: true
                  enable_body_collision_filters: true
                  enable_global_collision_filter: true
                  global_damping_factor: 0.18
                  global_damping_effective_velocity: 0.0
                  global_max_velocity: 25.0
                  enable_attachment_constraint: true
                  attachment_stiffness: [1000.0, 1000.0, 1000.0, 1000.0]
                  attachment_damping: [10.0, 0.0, 0.0, 0.0]
                  attachment_frames: 160
                  attachment_label_names: [lower_interface, right_collar, left_collar, strapless_top]
                  collar_attachment_height_offset_cm: 0.7
                  collar_vertical_attachment_stiffness: 350.0
                  collar_vertical_attachment_damping: 5.0
                  enable_cloth_reference_drag: true
                  cloth_reference_margin: 0.1
                  enable_body_smoothing: false
                  smoothing_total_smoothing_factor: 0.2
                  smoothing_recover_start_frame: 20
                  smoothing_frame_gap_between_steps: 2
                  smoothing_num_steps: 100
                  body_collision_thickness: 0.30
                  body_friction: 0.5
            render:
              config:
                resolution: [800, 800]
                sides: [front, back]
                front_camera_location: [0, 0.97, 4.15]
                uv_texture:
                  seam_width: 0.15
                  dpi: 300
                  fabric_grain_texture_path: ./assets/img/fabric_texture.png
                  fabric_grain_resolution: 5
            """;
    }
}
