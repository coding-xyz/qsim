#!/usr/bin/env julia

using Random
using LinearAlgebra
import QuantumToolbox

include(joinpath(@__DIR__, "_julia_runtime_common.jl"))

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

function _run_quantumtoolbox_native(times::Vector{Float64}, solver_mode::String, payload, run_options)
    ctx = _qubit_context(payload, times)
    n_qubits = Int(ctx["num_qubits"])
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
    if solver_mode == "se"
        sol = QuantumToolbox.sesolve(H, psi0, times; e_ops=e_ops, progress_bar=Val(false), dtmax=dtmax)
        states = _qt_expect_rows(sol.expect, length(times), n_qubits)
        solver_impl = "quantumtoolbox.sesolve"
    elseif solver_mode == "mcwf"
        ntraj = max(1, _safe_int(get(run_options, "ntraj", 128), 128))
        rng = Random.MersenneTwister(_safe_int(get(run_options, "seed", 12345), 12345))
        if isempty(c_ops)
            sol = QuantumToolbox.sesolve(H, psi0, times; e_ops=e_ops, progress_bar=Val(false), dtmax=dtmax)
            solver_impl = "quantumtoolbox.sesolve"
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
            )
            solver_impl = "quantumtoolbox.mcsolve"
        end
        states = _qt_expect_rows(sol.expect, length(times), n_qubits)
        collapse_counts["ntraj"] = ntraj
    else
        sol = QuantumToolbox.mesolve(H, psi0, times, c_ops; e_ops=e_ops, progress_bar=Val(false), dtmax=dtmax)
        states = _qt_expect_rows(sol.expect, length(times), n_qubits)
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
    payload = get(model_spec, "payload", Dict{String, Any}())
    run_options = Dict{String, Any}(Base.invokelatest(getfield, Main, :run_options))

    dt = _safe_float(get(model_spec, "dt", 1.0), 1.0)
    t_end = _safe_float(get(model_spec, "t_end", dt), dt)
    times = _build_times(dt, t_end)
    states, dyn_meta = _run_quantumtoolbox_native(times, solver_mode, payload, run_options)

    response = Dict(
        "schema_version" => "1.0",
        "engine" => "qtoolbox",
        "times" => times,
        "states" => states,
        "metadata" => Dict(
            "solver" => solver_mode,
            "state_encoding" => "per_qubit_excited_probability",
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
