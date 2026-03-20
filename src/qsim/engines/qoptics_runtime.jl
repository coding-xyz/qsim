#!/usr/bin/env julia

using Random
using LinearAlgebra
import QuantumOptics

include(joinpath(@__DIR__, "_julia_runtime_common.jl"))

function _qo_build_ops(ctx)
    n = Int(ctx["num_qubits"])
    b0 = QuantumOptics.SpinBasis(1 // 2)
    basis = n == 1 ? b0 : reduce(QuantumOptics.tensor, [b0 for _ in 1:n])
    sx = Any[]
    sy = Any[]
    sz = Any[]
    sm = Any[]
    sp = Any[]
    p1_ops = Any[]
    ident = n == 1 ? QuantumOptics.identityoperator(b0) : QuantumOptics.identityoperator(basis)
    local_sx = QuantumOptics.sigmax(b0)
    local_sy = QuantumOptics.sigmay(b0)
    local_sz = QuantumOptics.sigmaz(b0)
    local_sm = QuantumOptics.sigmap(b0)
    local_sp = QuantumOptics.sigmam(b0)
    for i in 1:n
        opx = n == 1 ? local_sx : QuantumOptics.embed(basis, basis, i, local_sx)
        opy = n == 1 ? local_sy : QuantumOptics.embed(basis, basis, i, local_sy)
        opz = n == 1 ? local_sz : QuantumOptics.embed(basis, basis, i, local_sz)
        opl = n == 1 ? local_sm : QuantumOptics.embed(basis, basis, i, local_sm)
        opr = n == 1 ? local_sp : QuantumOptics.embed(basis, basis, i, local_sp)
        push!(sx, opx)
        push!(sy, opy)
        push!(sz, opz)
        push!(sm, opl)
        push!(sp, opr)
        push!(p1_ops, 0.5 * (ident - opz))
    end
    psi0 = n == 1 ? QuantumOptics.spinup(b0) : reduce(QuantumOptics.tensor, [QuantumOptics.spinup(b0) for _ in 1:n])
    return Dict(
        "basis" => basis,
        "sx" => sx,
        "sy" => sy,
        "sz" => sz,
        "sm" => sm,
        "sp" => sp,
        "p1_ops" => p1_ops,
        "psi0" => psi0,
        "zero_op" => 0 * sx[1],
    )
end

function _qo_rows_from_states(states, p1_ops)
    rows = Vector{Vector{Float64}}()
    for state in states
        row = Float64[]
        for op in p1_ops
            push!(row, clamp(real(QuantumOptics.expect(op, state)), 0.0, 1.0))
        end
        push!(rows, row)
    end
    return rows
end

function _run_quantumoptics_native(times::Vector{Float64}, solver_mode::String, payload, run_options)
    ctx = _qubit_context(payload, times)
    n_qubits = Int(ctx["num_qubits"])
    ops = _qo_build_ops(ctx)
    H0 = _build_static_hamiltonian!(ops["zero_op"], payload, ctx, ops)
    coeffs, dyn_ops, selected_noise = _collect_dynamic_terms(payload, ctx, ops, run_options)
    H = isempty(dyn_ops) ? H0 : H0 + QuantumOptics.TimeDependentSum(Tuple(coeffs), Tuple(dyn_ops); init_time=times[1])
    c_ops, collapse_counts = _collect_jump_ops(payload, String(ctx["model_type"]), ops, n_qubits)
    psi0 = ops["psi0"]
    dtmax = _integration_dtmax(payload, times)

    solver_impl = ""
    states = Vector{Vector{Float64}}()
    if solver_mode == "se"
        _, psi_t = QuantumOptics.timeevolution.schroedinger_dynamic(times, psi0, H; dtmax=dtmax)
        states = _qo_rows_from_states(psi_t, ops["p1_ops"])
        solver_impl = "quantumoptics.timeevolution.schroedinger_dynamic"
    elseif solver_mode == "mcwf"
        ntraj = max(1, _safe_int(get(run_options, "ntraj", 128), 128))
        accum = [zeros(Float64, n_qubits) for _ in 1:length(times)]
        for traj in 1:ntraj
            seed = UInt(max(0, _safe_int(get(run_options, "seed", 12345), 12345) + traj))
            if isempty(c_ops)
                _, psi_t = QuantumOptics.timeevolution.schroedinger_dynamic(times, psi0, H; dtmax=dtmax)
            else
                _, psi_t = QuantumOptics.timeevolution.mcwf_dynamic(
                    times,
                    psi0,
                    H,
                    c_ops;
                    seed=seed,
                    dtmax=dtmax,
                    display_beforeevent=false,
                    display_afterevent=false,
                )
            end
            rows = _qo_rows_from_states(psi_t, ops["p1_ops"])
            for k in eachindex(rows)
                accum[k] .+= rows[k]
            end
        end
        states = [row ./ ntraj for row in accum]
        solver_impl = isempty(c_ops) ? "quantumoptics.timeevolution.schroedinger_dynamic" : "quantumoptics.timeevolution.mcwf_dynamic"
        collapse_counts["ntraj"] = ntraj
    else
        rho0 = QuantumOptics.dm(psi0)
        _, rho_t = QuantumOptics.timeevolution.master_dynamic(times, rho0, H, c_ops; dtmax=dtmax)
        states = _qo_rows_from_states(rho_t, ops["p1_ops"])
        solver_impl = "quantumoptics.timeevolution.master_dynamic"
    end

    meta = Dict(
        "solver_impl" => solver_impl,
        "model_type" => ctx["model_type"],
        "num_qubits" => n_qubits,
        "num_controls" => length(get(payload, "controls", Any[])),
        "num_collapse_ops" => length(c_ops),
        "selected_noise" => selected_noise,
        "frame_mode" => ctx["frame_mode"],
        "rwa" => ctx["rwa"],
        "dtmax" => dtmax,
        "collapse_counts" => collapse_counts,
    )
    return states, meta
end

function main()
    if length(ARGS) < 2
        error("usage: qoptics_runtime.jl <request.jl> <response.json>")
    end
    req_path = ARGS[1]
    out_path = ARGS[2]
    include(req_path)
    engine_package = lowercase(String(Base.invokelatest(getfield, Main, :engine_package)))
    if engine_package != "quantumoptics"
        error("qoptics_runtime.jl only supports engine_package=quantumoptics; got $(engine_package)")
    end
    solver_mode = lowercase(String(Base.invokelatest(getfield, Main, :solver_mode)))
    model_spec = Dict{String, Any}(Base.invokelatest(getfield, Main, :model_spec))
    payload = get(model_spec, "payload", Dict{String, Any}())
    run_options = Dict{String, Any}(Base.invokelatest(getfield, Main, :run_options))

    dt = _safe_float(get(model_spec, "dt", 1.0), 1.0)
    t_end = _safe_float(get(model_spec, "t_end", dt), dt)
    times = _build_times(dt, t_end)
    states, dyn_meta = _run_quantumoptics_native(times, solver_mode, payload, run_options)

    response = Dict(
        "schema_version" => "1.0",
        "engine" => "qoptics",
        "times" => times,
        "states" => states,
        "metadata" => Dict(
            "solver" => solver_mode,
            "state_encoding" => "per_qubit_excited_probability",
            "model_type" => get(payload, "model_type", "qubit_network"),
            "num_qubits" => _safe_int(get(payload, "num_qubits", 1), 1),
            "julia_version" => string(VERSION),
            "julia_backend" => "QuantumOptics",
            "julia_backend_version" => _pkg_ver_str(QuantumOptics),
            "native_solver" => true,
            "dynamic_model" => "payload_driven_native_package_solver",
            "details" => dyn_meta,
        ),
    )
    open(out_path, "w") do io
        write(io, _to_json(response))
    end
end

main()
