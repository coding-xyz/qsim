#!/usr/bin/env julia

using Random
using LinearAlgebra
import QuantumOptics
import QuantumToolbox

function _pkg_ver_str(mod)
    try
        return string(pkgversion(mod))
    catch
        return "unknown"
    end
end

function _safe_float(x, default::Float64=0.0)
    try
        return Float64(x)
    catch
        return default
    end
end

function _safe_int(x, default::Int=0)
    try
        return Int(round(Float64(x)))
    catch
        return default
    end
end

function _build_times(dt::Float64, t_end::Float64)
    step = max(dt, 1e-12)
    n = max(2, Int(floor(t_end / step)) + 1)
    return [i * step for i in 0:(n - 1)]
end

function _extract_rates(payload)
    gamma_down = 0.0
    gamma_up = 0.0
    gamma_phi = 0.0
    for item in get(payload, "collapse_operators", Any[])
        kind = lowercase(String(get(item, "kind", "")))
        rate = max(0.0, _safe_float(get(item, "rate_rad_s", get(item, "rate", 0.0)), 0.0))
        if kind == "relaxation"
            gamma_down += rate
        elseif kind == "excitation"
            gamma_up += rate
        elseif kind == "dephasing"
            gamma_phi += rate
        end
    end
    return gamma_down, gamma_up, gamma_phi
end

function _effective_omega(payload)
    vals = Float64[]
    for ctrl in get(payload, "controls", Any[])
        axis = lowercase(String(get(ctrl, "axis", "")))
        if axis != "x"
            continue
        end
        scale = _safe_float(get(ctrl, "scale", 1.0), 1.0)
        for v in get(ctrl, "values", Any[])
            push!(vals, abs(scale * _safe_float(v, 0.0)))
        end
    end
    if !isempty(vals)
        return sum(vals) / length(vals)
    end
    freqs = get(
        payload,
        "qubit_omega_rad_s",
        get(payload, "qubit_freqs_Hz", get(payload, "qubit_freqs_hz", Any[0.02])),
    )
    return isempty(freqs) ? 0.02 : abs(_safe_float(freqs[1], 0.02))
end

function _normalize_expect(v::Vector{Float64}, n::Int)
    if length(v) == n
        return v
    elseif length(v) > n
        return v[1:n]
    end
    out = copy(v)
    while length(out) < n
        push!(out, isempty(out) ? 0.0 : out[end])
    end
    return out
end

function _run_quantumoptics_native(times::Vector{Float64}, solver_mode::String, payload, run_options)
    b = QuantumOptics.SpinBasis(1 // 2)
    sx = QuantumOptics.sigmax(b)
    sz = QuantumOptics.sigmaz(b)
    sm = QuantumOptics.sigmam(b)
    sp = QuantumOptics.sigmap(b)

    gamma_down, gamma_up, gamma_phi = _extract_rates(payload)
    omega = _effective_omega(payload)
    delta = 0.0
    freq = get(
        payload,
        "qubit_omega_rad_s",
        get(payload, "qubit_freqs_Hz", get(payload, "qubit_freqs_hz", Any[0.0])),
    )
    if !isempty(freq)
        delta = _safe_float(freq[1], 0.0)
    end

    H = 0.5 * delta * sz + 0.5 * omega * sx

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

    psi0 = QuantumOptics.spindown(b)
    n = length(times)

    if solver_mode == "mcwf"
        ntraj = max(1, _safe_int(get(run_options, "ntraj", 128), 128))
        seed0 = _safe_int(get(run_options, "seed", 1234), 1234)
        accum = zeros(Float64, n)
        for k in 1:ntraj
            Random.seed!(seed0 + k)
            if isempty(rates)
                _, p1 = QuantumOptics.timeevolution.mcwf(
                    times,
                    psi0,
                    H,
                    J;
                    fout = (t, psi) -> real((1.0 - (QuantumOptics.expect(sz, psi) / (norm(psi)^2))) / 2.0),
                    display_beforeevent = false,
                    display_afterevent = false,
                )
            else
                _, p1 = QuantumOptics.timeevolution.mcwf(
                    times,
                    psi0,
                    H,
                    J;
                    rates = rates,
                    fout = (t, psi) -> real((1.0 - (QuantumOptics.expect(sz, psi) / (norm(psi)^2))) / 2.0),
                    display_beforeevent = false,
                    display_afterevent = false,
                )
            end
            p1v = _normalize_expect([_safe_float(x, 0.0) for x in p1], n)
            for i in 1:n
                accum[i] += p1v[i]
            end
        end
        p1mean = accum ./ ntraj
        states = [[1.0 - p, p] for p in p1mean]
        meta = Dict(
            "solver_impl" => "quantumoptics.timeevolution.mcwf",
            "ntraj" => ntraj,
            "gamma_down" => gamma_down,
            "gamma_up" => gamma_up,
            "gamma_phi" => gamma_phi,
            "omega_eff" => omega,
        )
        return states, meta
    else
        rho0 = QuantumOptics.dm(psi0)
        if isempty(rates)
            _, p1 = QuantumOptics.timeevolution.master(
                times,
                rho0,
                H,
                J;
                fout = (t, rho) -> real((1.0 - QuantumOptics.expect(sz, rho)) / 2.0),
            )
        else
            _, p1 = QuantumOptics.timeevolution.master(
                times,
                rho0,
                H,
                J;
                rates = rates,
                fout = (t, rho) -> real((1.0 - QuantumOptics.expect(sz, rho)) / 2.0),
            )
        end
        p1v = _normalize_expect([_safe_float(x, 0.0) for x in p1], n)
        states = [[1.0 - p, p] for p in p1v]
        meta = Dict(
            "solver_impl" => "quantumoptics.timeevolution.master",
            "gamma_down" => gamma_down,
            "gamma_up" => gamma_up,
            "gamma_phi" => gamma_phi,
            "omega_eff" => omega,
        )
        return states, meta
    end
end

function _qt_expect_vector(expect_obj, n::Int)
    if expect_obj isa AbstractMatrix
        return _normalize_expect([_safe_float(x, 0.0) for x in real.(collect(expect_obj[1, :]))], n)
    elseif expect_obj isa AbstractVector
        if isempty(expect_obj)
            return zeros(Float64, n)
        end
        firstv = expect_obj[1]
        if firstv isa Number
            return _normalize_expect([_safe_float(x, 0.0) for x in real.(expect_obj)], n)
        elseif firstv isa AbstractArray
            return _normalize_expect([_safe_float(x, 0.0) for x in real.(collect(firstv))], n)
        end
    end
    return zeros(Float64, n)
end

function _run_quantumtoolbox_native(times::Vector{Float64}, solver_mode::String, payload, run_options)
    sx = QuantumToolbox.sigmax()
    sz = QuantumToolbox.sigmaz()
    sm = QuantumToolbox.sigmam()
    sp = QuantumToolbox.sigmap()

    gamma_down, gamma_up, gamma_phi = _extract_rates(payload)
    omega = _effective_omega(payload)
    delta = 0.0
    freq = get(
        payload,
        "qubit_omega_rad_s",
        get(payload, "qubit_freqs_Hz", get(payload, "qubit_freqs_hz", Any[0.0])),
    )
    if !isempty(freq)
        delta = _safe_float(freq[1], 0.0)
    end

    H = 0.5 * delta * sz + 0.5 * omega * sx

    c_ops = Any[]
    if gamma_down > 0
        push!(c_ops, sqrt(gamma_down) * sm)
    end
    if gamma_up > 0
        push!(c_ops, sqrt(gamma_up) * sp)
    end
    if gamma_phi > 0
        push!(c_ops, sqrt(gamma_phi) * sz)
    end

    psi0 = QuantumToolbox.basis(2, 0)
    p1_op = 0.5 * (QuantumToolbox.qeye(2) - sz)

    n = length(times)
    if isempty(c_ops)
        sol = QuantumToolbox.sesolve(
            H,
            psi0,
            times;
            e_ops = [p1_op],
            progress_bar = Val(false),
        )
        p1 = _qt_expect_vector(sol.expect, n)
        states = [[1.0 - p, p] for p in p1]
        meta = Dict(
            "solver_impl" => "quantumtoolbox.sesolve",
            "gamma_down" => gamma_down,
            "gamma_up" => gamma_up,
            "gamma_phi" => gamma_phi,
            "omega_eff" => omega,
        )
        if solver_mode == "mcwf"
            meta["ntraj"] = max(1, _safe_int(get(run_options, "ntraj", 128), 128))
            meta["mcwf_reduced_to_unitary"] = true
        end
        return states, meta
    end
    if solver_mode == "mcwf"
        ntraj = max(1, _safe_int(get(run_options, "ntraj", 128), 128))
        seed0 = _safe_int(get(run_options, "seed", 1234), 1234)
        sol = QuantumToolbox.mcsolve(
            H,
            psi0,
            times,
            c_ops;
            e_ops = [p1_op],
            ntraj = ntraj,
            seed = seed0,
            progress_bar = Val(false),
        )
        p1 = _qt_expect_vector(sol.expect, n)
        states = [[1.0 - p, p] for p in p1]
        meta = Dict(
            "solver_impl" => "quantumtoolbox.mcsolve",
            "ntraj" => ntraj,
            "gamma_down" => gamma_down,
            "gamma_up" => gamma_up,
            "gamma_phi" => gamma_phi,
            "omega_eff" => omega,
        )
        return states, meta
    else
        rho0 = QuantumToolbox.ket2dm(psi0)
        sol = QuantumToolbox.mesolve(
            H,
            rho0,
            times,
            c_ops;
            e_ops = [p1_op],
            progress_bar = Val(false),
        )
        p1 = _qt_expect_vector(sol.expect, n)
        states = [[1.0 - p, p] for p in p1]
        meta = Dict(
            "solver_impl" => "quantumtoolbox.mesolve",
            "gamma_down" => gamma_down,
            "gamma_up" => gamma_up,
            "gamma_phi" => gamma_phi,
            "omega_eff" => omega,
        )
        return states, meta
    end
end

function _run_native(engine_package::String, times::Vector{Float64}, solver_mode::String, payload, run_options)
    key = lowercase(strip(engine_package))
    if key == "quantumoptics"
        return _run_quantumoptics_native(times, solver_mode, payload, run_options), "QuantumOptics"
    elseif key == "quantumtoolbox"
        return _run_quantumtoolbox_native(times, solver_mode, payload, run_options), "QuantumToolbox"
    end
    error("unsupported engine_package: $(engine_package)")
end

function _json_escape(s::AbstractString)
    io = IOBuffer()
    for c in s
        if c == '"'
            write(io, "\\\"")
        elseif c == '\\'
            write(io, "\\\\")
        elseif c == '\n'
            write(io, "\\n")
        elseif c == '\r'
            write(io, "\\r")
        elseif c == '\t'
            write(io, "\\t")
        else
            write(io, c)
        end
    end
    return String(take!(io))
end

function _to_json(x)
    if x === nothing
        return "null"
    elseif x isa Bool
        return x ? "true" : "false"
    elseif x isa Integer
        return string(x)
    elseif x isa AbstractFloat
        if isnan(x) || isinf(x)
            return "null"
        end
        return string(x)
    elseif x isa AbstractString
        return "\"" * _json_escape(x) * "\""
    elseif x isa Dict
        parts = String[]
        for (k, v) in x
            push!(parts, _to_json(string(k)) * ":" * _to_json(v))
        end
        return "{" * join(parts, ",") * "}"
    elseif x isa AbstractArray
        return "[" * join((_to_json(v) for v in x), ",") * "]"
    else
        return _to_json(string(x))
    end
end

function main()
    if length(ARGS) < 2
        error("usage: julia_engine_bridge.jl <request.jl> <response.json>")
    end
    req_path = ARGS[1]
    out_path = ARGS[2]
    include(req_path)
    engine_package = String(Base.invokelatest(getfield, Main, :engine_package))
    solver_mode = lowercase(String(Base.invokelatest(getfield, Main, :solver_mode)))
    if solver_mode == "se"
        solver_mode = "me"
    end
    model_spec = Dict{String, Any}(Base.invokelatest(getfield, Main, :model_spec))
    payload = get(model_spec, "payload", Dict{String, Any}())
    run_options = Dict{String, Any}(Base.invokelatest(getfield, Main, :run_options))

    dt = _safe_float(get(model_spec, "dt", 1.0), 1.0)
    t_end = _safe_float(get(model_spec, "t_end", dt), dt)
    times = _build_times(dt, t_end)

    (states, dyn_meta), backend_name = _run_native(engine_package, times, solver_mode, payload, run_options)

    response = Dict(
        "schema_version" => "1.0",
        "engine" => "julia-" * lowercase(engine_package),
        "times" => times,
        "states" => states,
        "metadata" => Dict(
            "solver" => solver_mode,
            "julia_version" => string(VERSION),
            "julia_backend" => backend_name,
            "julia_backend_version" => backend_name == "QuantumOptics" ? _pkg_ver_str(QuantumOptics) : _pkg_ver_str(QuantumToolbox),
            "bridge" => "subprocess_julia_literal",
            "native_solver" => true,
            "dynamic_model" => "native_package_solver",
            "details" => dyn_meta,
        ),
    )
    open(out_path, "w") do io
        write(io, _to_json(response))
    end
end

main()
