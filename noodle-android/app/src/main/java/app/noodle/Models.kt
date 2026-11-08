package app.noodle

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull

@Serializable
data class Entity(
    val key: String,
    val kind: String,
    val name: String,
    val state: JsonElement? = null,
    val brightness: Int? = null,
    val unit: String? = null,
    @SerialName("device_class") val deviceClass: String? = null,
    val actions: List<String>? = null,
    val attrs: Map<String, JsonElement>? = null,
) {
    private fun attr(name: String) = (attrs?.get(name) as? JsonPrimitive)?.doubleOrNull
    val min: Float? get() = attr("min")?.toFloat()
    val max: Float? get() = attr("max")?.toFloat()
    val step: Float? get() = attr("step")?.toFloat()
    /** A thermostat's mode ("heat", "off", ...), when it reports one. */
    val mode: String? get() = (attrs?.get("mode") as? JsonPrimitive)?.takeIf { it !is JsonNull }?.content
    private val prim get() = state as? JsonPrimitive
    val on: Boolean? get() = if (state is JsonNull) null else prim?.booleanOrNull
    val number: Double? get() = if (state is JsonNull) null else prim?.doubleOrNull
    val known: Boolean get() = state != null && state !is JsonNull
    val text: String
        get() {
            val p = prim ?: return "–"
            if (state is JsonNull) return "–"
            p.booleanOrNull?.let { return if (it) "on" else "off" }
            p.doubleOrNull?.let { n ->
                val s = if (n == Math.floor(n) && Math.abs(n) < 1e9) n.toLong().toString() else "%.1f".format(n)
                return if (unit != null) "$s $unit" else s
            }
            return p.content
        }
}

@Serializable
data class Device(
    val id: String,
    val source: String,
    val name: String,
    val model: String? = null,
    val manufacturer: String? = null,
    val available: Boolean = true,
    val battery: Int? = null,
    val area: String? = null,
    val entities: List<Entity> = emptyList(),
)
