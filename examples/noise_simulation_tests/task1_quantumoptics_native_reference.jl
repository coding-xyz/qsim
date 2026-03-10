#!/usr/bin/env julia

# Native QuantumOptics.jl reference for Task1 single-qubit baseline/detuned.
# This follows the same simplified effective model used by
# scripts/julia_engine_bridge.jl for cross-check purposes.

using QuantumOptics
using Statistics
using JSON

function rates_from_T1_T2(T1::Float64, T2::Float64; Tup::Float64=0.0)
    gamma_down = T1 > 0 ? 1.0 / T1 : 0.0
    gamma_up = Tup > 0 ? 1.0 / Tup : 0.0
    gamma_phi = T2 > 0 ? max(0.0, (1.0 / T2) - 0.5 * (gamma_down + gamma_up)) : 0.0
    return gamma_down, gamma_up, gamma_phi
end

function run_case(; delta::Float64, omega::Float64, T1::Float64, T2::Float64, t_end::Float64, dt::Float64)
    b = SpinBasis(1 // 2)
    sx = sigmax(b)
    sz = sigmaz(b)
    sm = sigmam(b)
    sp = sigmap(b)
    psi0 = spinup(b)
    rho0 = dm(psi0)

    H = 0.5 * delta * sz + 0.5 * omega * sx
    gamma_down, gamma_up, gamma_phi = rates_from_T1_T2(T1, T2)

    J = Any[]
    rates = Float64[]
    if gamma_down > 0
        push!(J, sm)
        push!(rates, gamma_down)
    end
    if gamma_up > 0
        push!(J, sp)
        push!(rates, gamma_up)
    end
    if gamma_phi > 0
        push!(J, sz)
        push!(rates, gamma_phi)
    end

    times = collect(0.0:dt:t_end)
    _, p1 = timeevolution.master(
        times,
        rho0,
        H,
        J;
        rates=rates,
        fout=(t, rho) -> real((1.0 - expect(sz, rho)) / 2.0),
    )
    return times, Float64.(p1)
end

omega_eff = 0.08
cases = Dict(
    "baseline" => (delta=5.0, T1=120.0, T2=90.0, t_end=240.0, dt=1.0),
    "detuned" => (delta=5.2, T1=80.0, T2=55.0, t_end=256.0, dt=1.0),
)
result = Dict(
    "engine" => "julia_qoptics_native",
    "cases" => Dict{String, Any}(),
)

for (name, cfg) in sort(collect(cases))
    t, p1 = run_case(
        delta=cfg.delta,
        omega=omega_eff,
        T1=cfg.T1,
        T2=cfg.T2,
        t_end=cfg.t_end,
        dt=cfg.dt,
    )

    result["cases"][name] = Dict(
        "times" => Float64.(t),
        "p1_t" => Float64.(p1),
        "final_p1" => Float64(p1[end]),
        "samples" => length(t),
        "params" => Dict(
            "delta" => cfg.delta,
            "omega" => omega_eff,
            "T1" => cfg.T1,
            "T2" => cfg.T2,
            "t_end" => cfg.t_end,
            "dt" => cfg.dt,
        ),
    )
end

println(JSON.json(result))