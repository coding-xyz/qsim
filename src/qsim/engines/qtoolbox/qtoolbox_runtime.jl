#!/usr/bin/env julia

using Random
using LinearAlgebra
import QuantumToolbox

include(joinpath(@__DIR__, "..", "_julia_runtime_common.jl"))

function _qt_tensor_n(ops)
    if length(ops) == 1
        return ops[1]
    end
    acc = ops[1]
    for op in ops[2:end]
        acc = QuantumToolbox.kron(acc, op)
    end
    return acc
end

function _qt_build_ops(ctx)
    n = Int(ctx["num_qubits"])
    model_type = String(ctx["model_type"])
    if model_type == "qubit_network"
        return _qt_build_qubit_ops(n)
    elseif model_type == "transmon_nlevel"
        return _qt_build_nlevel_ops(n, Int(ctx["transmon_levels"]))
    end
    return _qt_build_cqed_ops(n, Int(ctx["transmon_levels"]), Int(ctx["cavity_nmax"]))
end

function _qt_build_qubit_ops(n::Int)
    sx0 = QuantumToolbox.sigmax()
    sy0 = QuantumToolbox.sigmay()
    sz0 = QuantumToolbox.sigmaz()
    sm0 = QuantumToolbox.sigmap()
    sp0 = QuantumToolbox.sigmam()
    id0 = QuantumToolbox.qeye(2)
    sx = Any[]
    sy = Any[]
    sz = Any[]
    sm = Any[]
    sp = Any[]
    p1_ops = Any[]
    ident = _qt_tensor_n([id0 for _ in 1:n])
    for i in 1:n
        push!(sx, _qt_tensor_n([j == i ? sx0 : id0 for j in 1:n]))
        push!(sy, _qt_tensor_n([j == i ? sy0 : id0 for j in 1:n]))
        op_z = _qt_tensor_n([j == i ? sz0 : id0 for j in 1:n])
        push!(sz, op_z)
        push!(sm, _qt_tensor_n([j == i ? sm0 : id0 for j in 1:n]))
        push!(sp, _qt_tensor_n([j == i ? sp0 : id0 for j in 1:n]))
        push!(p1_ops, 0.5 * (ident - op_z))
    end
    psi0 = _qt_tensor_n([QuantumToolbox.basis(2, 0) for _ in 1:n])
    return Dict(
        "ident" => ident,
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

function _qt_build_nlevel_ops(n::Int, levels::Int)
    a0 = QuantumToolbox.destroy(levels)
    adag0 = QuantumToolbox.create(levels)
    n0 = QuantumToolbox.num(levels)
    id0 = QuantumToolbox.qeye(levels)
    p10 = QuantumToolbox.basis(levels, 1) * QuantumToolbox.basis(levels, 1)'
    sx = Any[]
    sy = Any[]
    sz = Any[]
    sm = Any[]
    sp = Any[]
    p1_ops = Any[]
    ident = _qt_tensor_n([id0 for _ in 1:n])
    for i in 1:n
        op_a = _qt_tensor_n([j == i ? a0 : id0 for j in 1:n])
        op_adag = _qt_tensor_n([j == i ? adag0 : id0 for j in 1:n])
        op_n = _qt_tensor_n([j == i ? n0 : id0 for j in 1:n])
        op_p1 = _qt_tensor_n([j == i ? p10 : id0 for j in 1:n])
        push!(sm, op_a)
        push!(sp, op_adag)
        push!(sz, op_n)
        push!(sx, op_a + op_adag)
        push!(sy, -1im * (op_a - op_adag))
        push!(p1_ops, op_p1)
    end
    psi0 = _qt_tensor_n([QuantumToolbox.basis(levels, 0) for _ in 1:n])
    return Dict(
        "ident" => ident,
        "sx" => sx,
        "sy" => sy,
        "sz" => sz,
        "sm" => sm,
        "sp" => sp,
        "p1_ops" => p1_ops,
        "psi0" => psi0,
        "zero_op" => 0 * sz[1],
    )
end

function _qt_build_cqed_ops(n::Int, levels::Int, cavity_nmax::Int)
    nc = cavity_nmax + 1
    a_c0 = QuantumToolbox.destroy(nc)
    adag_c0 = QuantumToolbox.create(nc)
    n_c0 = QuantumToolbox.num(nc)
    idc = QuantumToolbox.qeye(nc)
    a0 = QuantumToolbox.destroy(levels)
    adag0 = QuantumToolbox.create(levels)
    n0 = QuantumToolbox.num(levels)
    id0 = QuantumToolbox.qeye(levels)
    p10 = QuantumToolbox.basis(levels, 1) * QuantumToolbox.basis(levels, 1)'
    ident = _qt_tensor_n(vcat([idc], [id0 for _ in 1:n]))
    a_c = _qt_tensor_n(vcat([a_c0], [id0 for _ in 1:n]))
    adag_c = _qt_tensor_n(vcat([adag_c0], [id0 for _ in 1:n]))
    n_c = _qt_tensor_n(vcat([n_c0], [id0 for _ in 1:n]))
    sx = Any[]
    sy = Any[]
    sz = Any[]
    sm = Any[]
    sp = Any[]
    p1_ops = Any[]
    for i in 1:n
        qubit_ops = [j == i ? a0 : id0 for j in 1:n]
        qubit_adag_ops = [j == i ? adag0 : id0 for j in 1:n]
        qubit_n_ops = [j == i ? n0 : id0 for j in 1:n]
        qubit_p1_ops = [j == i ? p10 : id0 for j in 1:n]
        op_a = _qt_tensor_n(vcat([idc], qubit_ops))
        op_adag = _qt_tensor_n(vcat([idc], qubit_adag_ops))
        op_n = _qt_tensor_n(vcat([idc], qubit_n_ops))
        op_p1 = _qt_tensor_n(vcat([idc], qubit_p1_ops))
        push!(sm, op_a)
        push!(sp, op_adag)
        push!(sz, op_n)
        push!(sx, op_a + op_adag)
        push!(sy, -1im * (op_a - op_adag))
        push!(p1_ops, op_p1)
    end
    psi0 = _qt_tensor_n(vcat([QuantumToolbox.basis(nc, 0)], [QuantumToolbox.basis(levels, 0) for _ in 1:n]))
    return Dict(
        "ident" => ident,
        "a_c" => a_c,
        "adag_c" => adag_c,
        "n_c" => n_c,
        "sx" => sx,
        "sy" => sy,
        "sz" => sz,
        "sm" => sm,
        "sp" => sp,
        "p1_ops" => p1_ops,
        "psi0" => psi0,
        "zero_op" => 0 * ident,
    )
end

function _qt_expect_rows(expect_obj, n_times::Int, n_qubits::Int)
    rows = [zeros(Float64, n_qubits) for _ in 1:n_times]
    if expect_obj isa AbstractMatrix
        nr = min(size(expect_obj, 1), n_qubits)
        nc = min(size(expect_obj, 2), n_times)
        for i in 1:nr
            for k in 1:nc
                rows[k][i] = clamp(_safe_float(real(expect_obj[i, k]), 0.0), 0.0, 1.0)
            end
        end
        return rows
    end
    if expect_obj isa AbstractVector
        nr = min(length(expect_obj), n_qubits)
        for i in 1:nr
            vec = expect_obj[i]
            if vec isa AbstractArray
                nc = min(length(vec), n_times)
                for k in 1:nc
                    rows[k][i] = clamp(_safe_float(real(vec[k]), 0.0), 0.0, 1.0)
                end
            end
        end
    end
    return rows
end

function _qt_quantum_saveat(times::Vector{Float64}, trajectory_cfg, requested_state_kind::String)
    requested = lowercase(String(requested_state_kind))
    if !(requested in ("wave_function", "density_matrix"))
        return nothing
    end
    save_times = lowercase(String(get(trajectory_cfg, "save_times", "all")))
    save_final_state = Bool(get(trajectory_cfg, "save_final_state", true))
    if save_times != "none"
        return times
    end
    if save_final_state
        return [times[end]]
    end
    return nothing
end

function _run_quantumtoolbox_native(times::Vector{Float64}, solver_mode::String, payload, run_options)
    ctx = _qubit_context(payload, times)
    n_qubits = Int(ctx["num_qubits"])
    analyser_cfg = get(payload, "analyser", Dict{String, Any}())
    trajectory_cfg = get(analyser_cfg, "trajectory", Dict{String, Any}())
    requested_state_kind = lowercase(String(get(trajectory_cfg, "quantum", "")))
    if isempty(requested_state_kind)
        requested_state_kind = solver_mode == "mcwf" ? "wave_function" : "density_matrix"
    end
    state_saveat = _qt_quantum_saveat(times, trajectory_cfg, requested_state_kind)
    ops = _qt_build_ops(ctx)
    H0 = _build_static_hamiltonian!(ops["zero_op"], payload, ctx, ops)
    coeffs, dyn_ops, selected_noise = _collect_dynamic_terms(payload, ctx, ops, run_options)
    H = H0
    for idx in eachindex(dyn_ops)
        coef = coeffs[idx]
        H = H + QuantumToolbox.QobjEvo(dyn_ops[idx], (_p, t) -> coef(t))
    end
    c_ops, collapse_counts = _collect_jump_ops(payload, String(ctx["model_type"]), ops, n_qubits)
    psi0 = ops["psi0"]
    e_ops = ops["p1_ops"]
    dtmax = _integration_dtmax(payload, times)

    solver_impl = ""
    quantum_state_trajectory = nothing
    state_series = Any[]
    if solver_mode == "se"
        if state_saveat === nothing
            sol = QuantumToolbox.sesolve(H, psi0, times; e_ops=e_ops, progress_bar=Val(false), dtmax=dtmax)
        else
            sol = QuantumToolbox.sesolve(H, psi0, times; e_ops=e_ops, progress_bar=Val(false), dtmax=dtmax, saveat=state_saveat)
        end
        states = _qt_expect_rows(sol.expect, length(times), n_qubits)
        state_series = hasproperty(sol, :states) ? getproperty(sol, :states) : Any[]
        quantum_state_trajectory = _serialize_quantum_state_trajectory(state_series, requested_state_kind)
        solver_impl = "quantumtoolbox.sesolve"
    elseif solver_mode == "mcwf"
        ntraj = max(1, _safe_int(get(run_options, "ntraj", 128), 128))
        rng = Random.MersenneTwister(_safe_int(get(run_options, "seed", 12345), 12345))
        if isempty(c_ops)
            if state_saveat === nothing
                sol = QuantumToolbox.sesolve(H, psi0, times; e_ops=e_ops, progress_bar=Val(false), dtmax=dtmax)
            else
                sol = QuantumToolbox.sesolve(H, psi0, times; e_ops=e_ops, progress_bar=Val(false), dtmax=dtmax, saveat=state_saveat)
            end
            solver_impl = "quantumtoolbox.sesolve"
        else
            if state_saveat === nothing
                sol = QuantumToolbox.mcsolve(
                    H,
                    psi0,
                    times,
                    c_ops;
                    e_ops=e_ops,
                    ntraj=ntraj,
                    progress_bar=Val(false),
                    rng=rng,
                    dtmax=dtmax,
                )
            else
                sol = QuantumToolbox.mcsolve(
                    H,
                    psi0,
                    times,
                    c_ops;
                    e_ops=e_ops,
                    ntraj=ntraj,
                    progress_bar=Val(false),
                    rng=rng,
                    dtmax=dtmax,
                    saveat=state_saveat,
                )
            end
            solver_impl = "quantumtoolbox.mcsolve"
        end
        states = _qt_expect_rows(sol.expect, length(times), n_qubits)
        state_series = hasproperty(sol, :states) ? getproperty(sol, :states) : Any[]
        quantum_state_trajectory = _serialize_quantum_state_trajectory(state_series, requested_state_kind)
        collapse_counts["ntraj"] = ntraj
    else
        if state_saveat === nothing
            sol = QuantumToolbox.mesolve(H, psi0, times, c_ops; e_ops=e_ops, progress_bar=Val(false), dtmax=dtmax)
        else
            sol = QuantumToolbox.mesolve(H, psi0, times, c_ops; e_ops=e_ops, progress_bar=Val(false), dtmax=dtmax, saveat=state_saveat)
        end
        states = _qt_expect_rows(sol.expect, length(times), n_qubits)
        state_series = hasproperty(sol, :states) ? getproperty(sol, :states) : Any[]
        quantum_state_trajectory = _serialize_quantum_state_trajectory(state_series, requested_state_kind)
        solver_impl = "quantumtoolbox.mesolve"
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
    if quantum_state_trajectory !== nothing
        meta["quantum_state_trajectory"] = quantum_state_trajectory
    end
    return states, meta
end

function main()
    if length(ARGS) < 2
        error("usage: qtoolbox_runtime.jl <request.jl> <response.json>")
    end
    req_path = ARGS[1]
    out_path = ARGS[2]
    include(req_path)
    engine_package = lowercase(String(Base.invokelatest(getfield, Main, :engine_package)))
    if engine_package != "quantumtoolbox"
        error("qtoolbox_runtime.jl only supports engine_package=quantumtoolbox; got $(engine_package)")
    end
    solver_mode = lowercase(String(Base.invokelatest(getfield, Main, :solver_mode)))
    model_spec = Dict{String, Any}(Base.invokelatest(getfield, Main, :model_spec))
    payload = _typed_model_payload(model_spec)
    run_options = Dict{String, Any}(Base.invokelatest(getfield, Main, :run_options))

    time_cfg = Dict{String, Any}(get(model_spec, "time", Dict{String, Any}()))
    dt = _safe_float(get(time_cfg, "dt_s", get(model_spec, "dt", 1.0)), 1.0)
    t_end = _safe_float(get(time_cfg, "t_end_s", get(model_spec, "t_end", dt)), dt)
    times = _build_times(dt, t_end)
    states, dyn_meta = _run_quantumtoolbox_native(times, solver_mode, payload, run_options)

    response = Dict(
        "schema_version" => "1.0",
        "engine" => "qtoolbox",
        "times" => times,
        "states" => states,
        "metadata" => Dict(
            "solver" => solver_mode,
            "model_type" => get(payload, "model_type", "qubit_network"),
            "num_qubits" => _safe_int(get(payload, "num_qubits", 1), 1),
            "julia_version" => string(VERSION),
            "julia_backend" => "QuantumToolbox",
            "julia_backend_version" => _pkg_ver_str(QuantumToolbox),
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


