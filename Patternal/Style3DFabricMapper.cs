namespace Patterna;

public sealed record Style3DFabricParameters(
    double DensityKilogramsPerSquareMeter,
    double PhysicalThicknessCentimeters,
    double SelfContactThicknessCentimeters,
    double WeftStiffness,
    double WarpStiffness,
    double ShearStiffness,
    double BendWeft,
    double BendWarp,
    double BendBias,
    double BodyFriction);

public static class Style3DFabricMapper
{
    public static Style3DFabricParameters Map(FabricPhysicsDocument fabric)
    {
        ArgumentNullException.ThrowIfNull(fabric);
        double bendScale = Math.Clamp(fabric.BendResistance / 38.0, 0.10, 8.0);
        double physicalThicknessCm = Math.Clamp(
            fabric.ThicknessMillimeters / 10.0,
            0.005,
            0.10);
        return new Style3DFabricParameters(
            Math.Clamp(fabric.MassGramsPerSquareMeter / 1000.0, 0.02, 0.80),
            physicalThicknessCm,
            Math.Clamp(Math.Max(0.15, physicalThicknessCm * 2.5), 0.15, 0.30),
            Math.Clamp(400.0 * 9.0 / Math.Max(fabric.WeftStretchPercent, 0.1), 80.0, 4000.0),
            Math.Clamp(400.0 * 4.95 / Math.Max(fabric.WarpStretchPercent, 0.1), 80.0, 4000.0),
            Math.Clamp(40.0 * 12.6 / Math.Max(fabric.BiasStretchPercent, 0.1), 8.0, 400.0),
            2.0e-5 * bendScale,
            1.0e-5 * bendScale,
            5.0e-6 * bendScale,
            Math.Clamp(fabric.DynamicFriction, 0.05, 1.0));
    }
}
