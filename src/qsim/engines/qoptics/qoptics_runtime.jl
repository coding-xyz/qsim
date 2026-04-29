#!/usr/bin/env julia

using Random
using LinearAlgebra
import QuantumOptics

include(joinpath(@__DIR__, "..", "_julia_runtime_common.jl"))

function _qo_build_ops(ctx)
    n = Int(ctx["num_qubits"])
    model_type = String(ctx["model_type"])
    if model_type == "qubit_network"
        return _qo_build_qubit_ops(n)
    elseif model_type == "transmon_nlevel"
        return _qo_build_nlevel_ops(n, Int(ctx["transmon_levels"]))
    end
    return _qo_build_cqed_ops(n, Int(ctx["transmon_levels"]), Int(ctx["cavity_nmax"]))
end

function _qo_build_qubit_ops(n::Int)
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

function _qo_build_nlevel_ops(n::Int, levels::Int)
    b0 = QuantumOptics.FockBasis(levels)
    basis = n == 1 ? b0 : reduce(QuantumOptics.tensor, [b0 for _ in 1:n])
    sx = Any[]
    sy = Any[]
    sz = Any[]
    sm = Any[]
    sp = Any[]
    p1_ops = Any[]
    ident = n == 1 ? QuantumOptics.identityoperator(b0) : QuantumOptics.identityoperator(basis)
    local_a = QuantumOptics.destroy(b0)
    local_adag = QuantumOptics.create(b0)
    local_n = QuantumOptics.number(b0)
    local_p1 = QuantumOptics.dm(QuantumOptics.fockstate(b0, 1))
    for i in 1:n
        op_a = n == 1 ? local_a : QuantumOptics.embed(basis, basis, i, local_a)
        op_adag = n == 1 ? local_adag : QuantumOptics.embed(basis, basis, i, local_adag)
        op_n = n == 1 ? local_n : QuantumOptics.embed(basis, basis, i, local_n)
        op_p1 = n == 1 ? local_p1 : QuantumOptics.embed(basis, basis, i, local_p1)
        push!(sm, op_a)
        push!(sp, op_adag)
        push!(sz, op_n)
        push!(sx, op_a + op_adag)
        push!(sy, -1im * (op_a - op_adag))
        push!(p1_ops, op_p1)
    end
    psi0 = n == 1 ? QuantumOptics.fockstate(b0, 0) : reduce(QuantumOptics.tensor, [QuantumOptics.fockstate(b0, 0) for _ in 1:n])
    return Dict(
        "basis" => basis,
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

function _qo_build_cqed_ops(n::Int, levels::Int, cavity_nmax::Int)
    bc = QuantumOptics.FockBasis(cavity_nmax + 1)
    bq = QuantumOptics.FockBasis(levels)
    factors = [bc]
    append!(factors, [bq for _ in 1:n])
    basis = reduce(QuantumOptics.tensor, factors)
    ident = QuantumOptics.identityoperator(basis)
    cavity_a_local = QuantumOptics.destroy(bc)
    cavity_adag_local = QuantumOptics.create(bc)
    cavity_n_local = QuantumOptics.number(bc)
    a_c = QuantumOptics.embed(basis, basis, 1, cavity_a_local)
    adag_c = QuantumOptics.embed(basis, basis, 1, cavity_adag_local)
    n_c = QuantumOptics.embed(basis, basis, 1, cavity_n_local)
    qubit_a_local = QuantumOptics.destroy(bq)
    qubit_adag_local = QuantumOptics.create(bq)
    qubit_n_local = QuantumOptics.number(bq)
    qubit_p1_local = QuantumOptics.dm(QuantumOptics.fockstate(bq, 1))
    sx = Any[]
    sy = Any[]
    sz = Any[]
    sm = Any[]
    sp = Any[]
    p1_ops = Any[]
    for i in 1:n
        idx = i + 1
        op_a = QuantumOptics.embed(basis, basis, idx, qubit_a_local)
        op_adag = QuantumOptics.embed(basis, basis, idx, qubit_adag_local)
        op_n = QuantumOptics.embed(basis, basis, idx, qubit_n_local)
        op_p1 = QuantumOptics.embed(basis, basis, idx, qubit_p1_local)
        push!(sm, op_a)
        push!(sp, op_adag)
        push!(sz, op_n)
        push!(sx, op_a + op_adag)
        push!(sy, -1im * (op_a - op_adag))
        push!(p1_ops, op_p1)
    end
    psi0 = QuantumOptics.tensor(QuantumOptics.fockstate(bc, 0), [QuantumOptics.fockstate(bq, 0) for _ in 1:n]...)
    return Dict(
        "basis" => basis,
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
    analyser_cfg = get(payload, "analyser", Dict{String, Any}())
    trajectory_cfg = get(analyser_cfg, "trajectory", Dict{String, Any}())
    requested_state_kind = lowercase(String(get(trajectory_cfg, "quantum", "")))
    if isempty(requested_state_kind)
        requested_state_kind = solver_mode == "mcwf" ? "wave_function" : "density_matrix"
    end
    ops = _qo_build_ops(ctx)
    H0 = _build_static_hamiltonian!(ops["zero_op"], payload, ctx, ops)
    coeffs, dyn_ops, selected_noise = _collect_dynamic_terms(payload, ctx, ops, run_options)
    H = isempty(dyn_ops) ? H0 : H0 + QuantumOptics.TimeDependentSum(Tuple(coeffs), Tuple(dyn_ops); init_time=times[1])
    c_ops, collapse_counts = _collect_jump_ops(payload, String(ctx["model_type"]), ops, n_qubits)
    psi0 = ops["psi0"]
    dtmax = _integration_dtmax(payload, times)

    solver_impl = ""
    states = Vector{Vector{Float64}}()
    quantum_state_trajectory = nothing
    if solver_mode == "se"
        _, psi_t = QuantumOptics.timeevolution.schroedinger_dynamic(times, psi0, H; dtmax=dtmax)
        states = _qo_rows_from_states(psi_t, ops["p1_ops"])
        quantum_state_trajectory = _serialize_quantum_state_trajectory(psi_t, requested_state_kind)
        solver_impl = "quantumoptics.timeevolution.schroedinger_dynamic"
    elseif solver_mode == "mcwf"
        ntraj = max(1, _safe_int(get(run_options, "ntraj", 128), 128))
        accum = [zeros(Float64, n_qubits) for _ in 1:length(times)]
        first_trace = Any[]
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
            if traj == 1
                first_trace = psi_t
            end
            rows = _qo_rows_from_states(psi_t, ops["p1_ops"])
            for k in eachindex(rows)
                accum[k] .+= rows[k]
            end
        end
        states = [row ./ ntraj for row in accum]
        quantum_state_trajectory = _serialize_quantum_state_trajectory(first_trace, requested_state_kind)
        solver_impl = isempty(c_ops) ? "quantumoptics.timeevolution.schroedinger_dynamic" : "quantumoptics.timeevolution.mcwf_dynamic"
        collapse_counts["ntraj"] = ntraj
    else
        rho0 = QuantumOptics.dm(psi0)
        _, rho_t = QuantumOptics.timeevolution.master_dynamic(times, rho0, H, c_ops; dtmax=dtmax)
        states = _qo_rows_from_states(rho_t, ops["p1_ops"])
        quantum_state_trajectory = _serialize_quantum_state_trajectory(rho_t, requested_state_kind)
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
    if quantum_state_trajectory !== nothing
        meta["quantum_state_trajectory"] = quantum_state_trajectory
    end
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
    payload = _typed_model_payload(model_spec)
    run_options = Dict{String, Any}(Base.invokelatest(getfield, Main, :run_options))

    time_cfg = Dict{String, Any}(get(model_spec, "time", Dict{String, Any}()))
    dt = _safe_float(get(time_cfg, "dt_s", get(model_spec, "dt", 1.0)), 1.0)
    t_end = _safe_float(get(time_cfg, "t_end_s", get(model_spec, "t_end", dt)), dt)
    times = _build_times(dt, t_end)
    states, dyn_meta = _run_quantumoptics_native(times, solver_mode, payload, run_options)

    response = Dict(
        "schema_version" => "1.0",
        "engine" => "qoptics",
        "times" => times,
        "states" => states,
        "metadata" => Dict(
            "solver" => solver_mode,
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


