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

function _asdict(value)
    try
        return Dict{String, Any}(value)
    catch
        return Dict{String, Any}()
    end
end

function _typed_control_payload(term)
    item = _asdict(term)
    op = _asdict(get(item, "operator", Dict{String, Any}()))
    coeff = _asdict(get(item, "coefficient", Dict{String, Any}()))
    carrier = _asdict(get(coeff, "carrier", Dict{String, Any}()))
    metadata = _asdict(get(item, "metadata", Dict{String, Any}()))
    out = Dict{String, Any}(
        "target" => get(op, "target", -1),
        "target_pair" => get(op, "target_pair", Any[]),
        "axis" => get(op, "name", "x"),
        "times" => get(coeff, "times_s", Any[]),
        "values" => get(coeff, "values", Any[]),
        "scale" => get(coeff, "scale", 1.0),
        "carrier_omega_rad_s" => get(carrier, "omega_rad_s", 0.0),
        "carrier_phase_rad" => get(carrier, "phase_rad", 0.0),
    )
    merge!(out, metadata)
    return out
end

function _typed_model_payload(model_spec)
    system = _asdict(get(model_spec, "system", Dict{String, Any}()))
    frame = _asdict(get(model_spec, "frame", Dict{String, Any}()))
    hamiltonian = _asdict(get(model_spec, "hamiltonian", Dict{String, Any}()))
    noise = _asdict(get(model_spec, "noise", Dict{String, Any}()))
    readout = _asdict(get(model_spec, "readout", Dict{String, Any}()))
    analysis_request = _asdict(get(model_spec, "analysis_request", Dict{String, Any}()))
    study = _asdict(get(model_spec, "study", Dict{String, Any}()))
    components = Any[_asdict(item) for item in get(system, "components", Any[])]
    connections = Any[_asdict(item) for item in get(system, "connections", Any[])]
    transmons = Any[item for item in components if lowercase(String(get(item, "type", ""))) == "transmon"]
    resonators = Any[item for item in components if lowercase(String(get(item, "type", ""))) in ("resonator", "cavity")]
    qubits = _asdict(get(system, "qubits", Dict{String, Any}()))
    cavity = _asdict(get(system, "cavity", Dict{String, Any}()))
    coupling_summary = _asdict(get(system, "couplings", Dict{String, Any}()))
    num_qubits = isempty(transmons) ? get(system, "num_qubits", get(qubits, "num_qubits", 1)) : length(transmons)
    transmon_levels = isempty(transmons) ? get(system, "transmon_levels", get(qubits, "transmon_levels", 2)) : maximum([_safe_int(get(item, "levels", 2), 2) for item in transmons])
    cavity_item = isempty(resonators) ? cavity : resonators[1]
    g_connections = Any[
        item for item in connections
        if lowercase(String(get(item, "type", ""))) in ("jc", "dispersive", "zz")
    ]
    return Dict{String, Any}(
        "model_type" => get(system, "model_type", "qubit_network"),
        "simulation_level" => get(system, "simulation_level", "qubit"),
        "num_qubits" => num_qubits,
        "transmon_levels" => transmon_levels,
        "cavity_nmax" => get(system, "cavity_nmax", get(cavity_item, "cavity_nmax", get(cavity_item, "nmax", 0))),
        "qubit_omega_rad_s" => isempty(transmons) ? get(system, "qubit_omega_rad_s", get(qubits, "qubit_omega_rad_s", Any[])) : Any[get(item, "omega_rad_s", 0.0) for item in transmons],
        "anharmonicity_rad_s" => isempty(transmons) ? get(system, "anharmonicity_rad_s", get(qubits, "anharmonicity_rad_s", Any[])) : Any[get(item, "anharmonicity_rad_s", 0.0) for item in transmons],
        "cavity_omega_rad_s" => get(system, "cavity_omega_rad_s", get(cavity_item, "cavity_omega_rad_s", get(cavity_item, "omega_rad_s", 0.0))),
        "g_cavity_rad_s" => isempty(g_connections) ? get(system, "g_cavity_rad_s", get(coupling_summary, "g_cavity_rad_s", Any[])) : Any[get(item, "g_rad_s", 0.0) for item in g_connections],
        "frame" => frame,
        "couplings" => get(hamiltonian, "coupling_terms", Any[]),
        "controls" => Any[_typed_control_payload(term) for term in get(hamiltonian, "control_terms", Any[])],
        "collapse_operators" => get(noise, "collapse_channels", Any[]),
        "noise_summary" => Dict{String, Any}(
            "selected_model" => get(noise, "selected_model", "markovian_lindblad"),
            "stochastic" => get(noise, "stochastic_channels", Any[]),
        ),
        "readout_controls" => get(readout, "controls", Any[]),
        "readout_chain" => get(readout, "chain", Dict{String, Any}()),
        "reset_events" => get(readout, "reset_events", Any[]),
        "noise_cfg" => Dict{String, Any}("readout_error" => get(noise, "readout_error", 0.0)),
        "analyser" => get(analysis_request, "config", Dict{String, Any}()),
        "study" => get(study, "steps", Any[]),
        "primary_step" => get(study, "primary_step", Dict{String, Any}()),
    )
end

function _build_times(dt::Float64, t_end::Float64)
    step = max(dt, 1e-12)
    n = max(2, Int(floor(t_end / step)) + 1)
    return [i * step for i in 0:(n - 1)]
end

function _float_list(value)
    out = Float64[]
    for item in value
        push!(out, _safe_float(item, 0.0))
    end
    return out
end

function _float_list_with_default(payload, key::String, n::Int)
    raw = get(payload, key, Any[])
    vals = _float_list(raw)
    if length(vals) < n
        append!(vals, zeros(Float64, n - length(vals)))
    end
    return vals[1:n]
end

function _normalize_series(values::Vector{Float64}, n::Int)
    if length(values) == n
        return values
    elseif length(values) > n
        return values[1:n]
    end
    out = copy(values)
    while length(out) < n
        push!(out, isempty(out) ? 0.0 : out[end])
    end
    return out
end

function _min_positive_step(values)::Float64
    if length(values) <= 1
        return Inf
    end
    best = Inf
    prev = _safe_float(values[1], 0.0)
    for item in values[2:end]
        curr = _safe_float(item, prev)
        delta = curr - prev
        if delta > 0.0 && delta < best
            best = delta
        end
        prev = curr
    end
    return best
end

function _coeff_interp(times::Vector{Float64}, values::Vector{Float64}, scale::Float64)
    xs = copy(times)
    ys = scale .* copy(values)
    if isempty(xs) || isempty(ys)
        return t -> 0.0
    end
    ys = _normalize_series(ys, length(xs))
    if length(xs) == 1
        c = ys[1]
        return t -> c
    end
    x0 = xs[1]
    x1 = xs[end]
    return function (t)
        tv = Float64(t)
        if tv <= x0
            return ys[1]
        elseif tv >= x1
            return ys[end]
        end
        idx = searchsortedlast(xs, tv)
        idx = clamp(idx, 1, length(xs) - 1)
        xa = xs[idx]
        xb = xs[idx + 1]
        ya = ys[idx]
        yb = ys[idx + 1]
        if xb <= xa
            return yb
        end
        alpha = (tv - xa) / (xb - xa)
        return ya + alpha * (yb - ya)
    end
end

function _modulated_coeff(envelope; omega_rad_s::Float64, phase_rad::Float64, trig::String)
    trig_key = lowercase(strip(trig))
    return function (t)
        env = _safe_float(envelope(t), 0.0)
        angle = omega_rad_s * _safe_float(t, 0.0) + phase_rad
        if trig_key == "sin"
            return env * sin(angle)
        end
        return env * cos(angle)
    end
end

function _dephasing_collapse_prefactor(rate::Float64, model_type::String)
    gamma = max(0.0, rate)
    if gamma <= 0.0
        return 0.0
    end
    if lowercase(strip(model_type)) == "qubit_network"
        return sqrt(0.5 * gamma)
    end
    return sqrt(2.0 * gamma)
end

function _one_over_f_trace(
    tlist::Vector{Float64},
    amp::Float64,
    fmin::Float64,
    fmax::Float64,
    exponent::Float64,
    ncomp::Int,
    rng::AbstractRNG,
)
    if amp <= 0.0 || length(tlist) <= 1
        return zeros(Float64, length(tlist))
    end
    f_lo = max(1e-9, fmin)
    nyquist = 0.5 / max(tlist[2] - tlist[1], 1e-12)
    f_hi = min(max(f_lo * 1.01, fmax), nyquist)
    if f_hi <= f_lo
        return zeros(Float64, length(tlist))
    end
    nfreq = max(8, ncomp)
    freqs = [10.0^(log10(f_lo) + (log10(f_hi) - log10(f_lo)) * (i - 1) / max(1, nfreq - 1)) for i in 1:nfreq]
    phases = [2.0 * pi * rand(rng) for _ in freqs]
    weights = [1.0 / max(f, 1e-12)^(0.5 * exponent) for f in freqs]
    wrms = sqrt(mean(abs2, weights))
    if wrms > 0.0
        weights ./= wrms
    end
    sig = zeros(Float64, length(tlist))
    for (k, t) in enumerate(tlist)
        acc = 0.0
        for i in eachindex(freqs)
            acc += weights[i] * sin(2.0 * pi * t * freqs[i] + phases[i])
        end
        sig[k] = acc
    end
    sig .-= mean(sig)
    rms = sqrt(mean(abs2, sig))
    if rms > 0.0
        sig .*= amp / rms
    end
    return sig
end

function _ou_trace(tlist::Vector{Float64}, sigma::Float64, tau::Float64, rng::AbstractRNG)
    if sigma <= 0.0 || length(tlist) <= 1
        return zeros(Float64, length(tlist))
    end
    dt = max(1e-12, tlist[2] - tlist[1])
    tau_eff = max(1e-9, tau)
    a = exp(-dt / tau_eff)
    b = sigma * sqrt(max(0.0, 1.0 - a * a))
    out = zeros(Float64, length(tlist))
    for k in 2:length(tlist)
        out[k] = a * out[k - 1] + b * randn(rng)
    end
    return out
end

function _qubit_context(payload, times::Vector{Float64})
    model_type = lowercase(String(get(payload, "model_type", "qubit_network")))
    if !(model_type in ("qubit_network", "transmon_nlevel", "cqed_jc"))
        error("Unsupported Julia engine model_type=$(model_type)")
    end
    n_qubits = max(1, _safe_int(get(payload, "num_qubits", 1), 1))
    freqs = _float_list_with_default(payload, "qubit_omega_rad_s", n_qubits)
    anh = _float_list_with_default(payload, "anharmonicity_rad_s", n_qubits)
    g_cavity = _float_list_with_default(payload, "g_cavity_rad_s", n_qubits)
    frame_cfg = get(payload, "frame", Dict{String, Any}())
    frame_mode = lowercase(String(get(frame_cfg, "mode", "rotating")))
    rwa = Bool(get(frame_cfg, "rwa", true))
    return Dict(
        "model_type" => model_type,
        "num_qubits" => n_qubits,
        "freqs" => freqs,
        "anh" => anh,
        "transmon_levels" => max(2, _safe_int(get(payload, "transmon_levels", 2), 2)),
        "cavity_nmax" => max(0, _safe_int(get(payload, "cavity_nmax", 0), 0)),
        "cavity_omega_rad_s" => _safe_float(get(payload, "cavity_omega_rad_s", 0.0), 0.0),
        "g_cavity_rad_s" => g_cavity,
        "frame_mode" => frame_mode,
        "rwa" => rwa,
        "times" => times,
    )
end

function _build_static_hamiltonian!(H0, payload, ctx, ops)
    n = Int(ctx["num_qubits"])
    model_type = String(ctx["model_type"])
    freqs = ctx["freqs"]
    anh = ctx["anh"]
    sx = ops["sx"]
    sy = ops["sy"]
    sz = ops["sz"]
    ident = ops["ident"]
    if model_type == "qubit_network"
        for i in 1:n
            H0 += 0.5 * freqs[i] * sz[i]
        end
    elseif model_type == "transmon_nlevel"
        for i in 1:n
            H0 += freqs[i] * sz[i] + 0.5 * anh[i] * (sz[i] * (sz[i] - ident))
        end
    else
        H0 += _safe_float(ctx["cavity_omega_rad_s"], 0.0) * ops["n_c"]
        for i in 1:n
            H0 += freqs[i] * sz[i] + 0.5 * anh[i] * (sz[i] * (sz[i] - ident))
        end
        g_cavity = ctx["g_cavity_rad_s"]
        for i in 1:n
            g = _safe_float(g_cavity[i], 0.0)
            if g != 0.0
                H0 += g * (ops["adag_c"] * ops["sm"][i] + ops["a_c"] * ops["sp"][i])
            end
        end
    end
    for item in get(payload, "couplings", Any[])
        i = _safe_int(get(item, "i", 0), 0) + 1
        j = _safe_int(get(item, "j", 0), 0) + 1
        if i < 1 || j < 1 || i > n || j > n || i == j
            continue
        end
        g = _safe_float(get(item, "coefficient_rad_s", get(item, "g_rad_s", get(item, "g", 0.0))), 0.0)
        kind = lowercase(String(get(item, "kind", "xx+yy")))
        if kind == "zz"
            H0 += g * (sz[i] * sz[j])
        elseif kind == "xx"
            H0 += g * (sx[i] * sx[j])
        else
            if model_type == "qubit_network"
                H0 += g * ((sx[i] * sx[j]) + (sy[i] * sy[j]))
            else
                H0 += g * (ops["sp"][i] * ops["sm"][j] + ops["sm"][i] * ops["sp"][j])
            end
        end
    end
    return H0
end

function _collect_dynamic_terms(payload, ctx, ops, run_options)
    n = Int(ctx["num_qubits"])
    frame_mode = String(ctx["frame_mode"])
    rwa = Bool(ctx["rwa"])
    sx = ops["sx"]
    sy = ops["sy"]
    sz = ops["sz"]
    coeffs = Function[]
    operators = Any[]
    for ctrl in get(payload, "controls", Any[])
        target = _safe_int(get(ctrl, "target", -1), -1) + 1
        if target < 1 || target > n
            continue
        end
        axis = lowercase(String(get(ctrl, "axis", "x")))
        envelope = _coeff_interp(
            _float_list(get(ctrl, "times", Any[])),
            _float_list(get(ctrl, "values", Any[])),
            _safe_float(get(ctrl, "scale", 1.0), 1.0),
        )
        if axis == "x"
            phase = _safe_float(get(ctrl, "carrier_phase_rad", 0.0), 0.0)
            carrier = _safe_float(get(ctrl, "carrier_omega_rad_s", 0.0), 0.0)
            delta = _safe_float(get(ctrl, "drive_delta_rad_s", 0.0), 0.0)
            if frame_mode == "rotating" && rwa
                push!(operators, sx[target])
                push!(coeffs, _modulated_coeff(envelope; omega_rad_s=delta, phase_rad=phase, trig="cos"))
                push!(operators, sy[target])
                push!(coeffs, _modulated_coeff(envelope; omega_rad_s=delta, phase_rad=phase, trig="sin"))
            else
                push!(operators, sx[target])
                push!(coeffs, _modulated_coeff(envelope; omega_rad_s=carrier, phase_rad=phase, trig="cos"))
            end
        elseif axis == "y"
            push!(operators, sy[target])
            push!(coeffs, envelope)
        elseif axis == "z"
            push!(operators, sz[target])
            push!(coeffs, envelope)
        end
    end

    noise_summary = get(payload, "noise_summary", Dict{String, Any}())
    selected_noise = lowercase(String(get(noise_summary, "selected_model", "markovian_lindblad")))
    stochastic = get(noise_summary, "stochastic", Any[])
    if selected_noise in ("one_over_f", "ou") && !isempty(stochastic)
        seed0 = _safe_int(get(run_options, "seed", 12345), 12345)
        ncomp = max(8, _safe_int(get(run_options, "one_over_f_components", 64), 64))
        times = ctx["times"]
        for item in stochastic
            target = _safe_int(get(item, "q", -1), -1) + 1
            if target < 1 || target > n
                continue
            end
            rng = Random.MersenneTwister(seed0 + 1000 + target)
            if selected_noise == "one_over_f"
                series = _one_over_f_trace(
                    times,
                    _safe_float(get(item, "one_over_f_amp_rad_s", get(item, "one_over_f_amp", 0.0)), 0.0),
                    _safe_float(get(item, "one_over_f_fmin", 1e-3), 1e-3),
                    _safe_float(get(item, "one_over_f_fmax", 0.5 / max(times[2] - times[1], 1e-12)), 0.5),
                    _safe_float(get(item, "one_over_f_exponent", 1.0), 1.0),
                    ncomp,
                    rng,
                )
            else
                series = _ou_trace(
                    times,
                    _safe_float(get(item, "ou_sigma_rad_s", get(item, "ou_sigma", 0.0)), 0.0),
                    _safe_float(get(item, "ou_tau", 1.0), 1.0),
                    rng,
                )
            end
            env = _coeff_interp(times, series, 1.0)
            push!(operators, sz[target])
            push!(coeffs, env)
        end
    end
    return coeffs, operators, selected_noise
end

function _collect_jump_ops(payload, model_type::String, ops, n_qubits::Int)
    c_ops = Any[]
    counts = Dict(
        "relaxation" => 0,
        "excitation" => 0,
        "dephasing" => 0,
    )
    for item in get(payload, "collapse_operators", Any[])
        target = _safe_int(get(item, "target", -1), -1) + 1
        if target < 1 || target > n_qubits
            continue
        end
        kind = lowercase(String(get(item, "kind", "relaxation")))
        rate = max(0.0, _safe_float(get(item, "rate_rad_s", get(item, "rate", 0.0)), 0.0))
        if rate <= 0.0
            continue
        end
        if kind == "relaxation"
            push!(c_ops, sqrt(rate) * ops["sm"][target])
            counts["relaxation"] += 1
        elseif kind == "excitation"
            push!(c_ops, sqrt(rate) * ops["sp"][target])
            counts["excitation"] += 1
        elseif kind == "dephasing"
            pref = _dephasing_collapse_prefactor(rate, model_type)
            if pref > 0.0
                push!(c_ops, pref * ops["sz"][target])
                counts["dephasing"] += 1
            end
        end
    end
    return c_ops, counts
end

function _integration_dtmax(payload, times::Vector{Float64})::Float64
    best = _min_positive_step(times)
    for ctrl in get(payload, "controls", Any[])
        ctrl_best = _min_positive_step(_float_list(get(ctrl, "times", Any[])))
        if ctrl_best < best
            best = ctrl_best
        end
    end
    if !isfinite(best) || best <= 0.0
        return 1e-12
    end
    return max(1e-12, best)
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

function _complex_pair(z)
    return [_safe_float(real(z), 0.0), _safe_float(imag(z), 0.0)]
end

function _serialize_quantum_state(state)
    dense = Array(state.data)
    if ndims(dense) == 1
        return Dict(
            "kind" => "wave_function",
            "data" => [Dict("__qsim_complex__" => [real(v), imag(v)]) for v in dense],
        )
    elseif ndims(dense) == 2 && (size(dense, 1) == 1 || size(dense, 2) == 1)
        vec = vec(dense)
        return Dict(
            "kind" => "wave_function",
            "data" => [Dict("__qsim_complex__" => [real(v), imag(v)]) for v in vec],
        )
    end
    return Dict(
        "kind" => "density_matrix",
        "data" => [[Dict("__qsim_complex__" => [real(v), imag(v)]) for v in row] for row in eachrow(dense)],
    )
end

function _serialize_quantum_state_trajectory(states, requested_kind::String)
    if isempty(states)
        return nothing
    end
    serialized = [_serialize_quantum_state(state) for state in states]
    actual_kind = String(get(serialized[1], "kind", "unknown"))
    note = requested_kind == "wave_function" && actual_kind != "wave_function" ? "requested wave_function but solver returned density_matrix" : ""
    return Dict(
        "requested_kind" => isempty(requested_kind) ? actual_kind : requested_kind,
        "actual_kind" => actual_kind,
        "encoding" => "complex",
        "snapshots" => [item["data"] for item in serialized],
        "note" => note,
    )
end
