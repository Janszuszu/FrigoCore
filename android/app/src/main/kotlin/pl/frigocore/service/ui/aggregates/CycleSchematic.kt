package pl.frigocore.service.ui.aggregates

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.runtime.getValue
import androidx.compose.ui.graphics.lerp
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import pl.frigocore.service.data.model.SensorResponse
import pl.frigocore.service.ui.common.Formatters
import pl.frigocore.service.ui.common.quietClickable
import pl.frigocore.service.ui.theme.Barlow

/*
 * The refrigeration cycle in the style of an industrial control panel
 * (HMI): muted colours only where they mean something — hot gas, liquid,
 * suction — equipment in one neutral line grey, one pipe weight throughout,
 * and the readings as instrument tags. Drawn from the same shapes as the
 * approved mockup (android/store/mockups/schemat-agregatu-v8.svg), in its
 * 720 x 640 coordinate space, scaled to the card.
 */

private const val W = 720f
private const val H = 640f

private val HotGas = Color(0xFFE0705F)
private val LiquidLine = Color(0xFFD6A94F)
private val Suction = Color(0xFF4FA6D8)
private val Equipment = Color(0xFFC3CEDD)
private val Fins = Color(0xFF2F3F56)
private val PipeShell = Color(0xFF050A12)
private val Plate = Color(0xFF0E1A2B)
private val Air = Color(0xFF5C6E87)
private val GridLine = Color(0xFF14233A)
private val Ground = Color(0xFF0A1320)

private fun svg(d: String): Path = PathParser().parsePathString(d).toPath()

private val FinsPath = svg(
    "M112,392 V548 M126,392 V548 M140,392 V548 M154,392 V548 M168,392 V548 M182,392 V548 M196,392 V548 M210,392 V548 M224,392 V548 M238,392 V548 " +
        "M482,392 V548 M496,392 V548 M510,392 V548 M524,392 V548 M538,392 V548 M552,392 V548 M566,392 V548 M580,392 V548 M594,392 V548 M608,392 V548",
)
private val LoopPath = svg(
    "M290,128 H130 Q86,128 86,172 V384 Q86,400 104,400 H246 A23,23 0 0 1 246,446 H104 A23,23 0 0 0 104,492 H246 A23,23 0 0 1 246,538 " +
        "H104 Q86,538 86,554 V576 Q86,600 110,600 H610 Q634,600 634,576 V554 Q634,538 616,538 H474 A23,23 0 0 1 474,492 H616 " +
        "A23,23 0 0 0 616,446 H474 A23,23 0 0 1 474,400 H616 Q634,400 634,384 V172 Q634,128 590,128 H480",
)
private val HotPath = svg("M290,128 H130 Q86,128 86,172 V384 Q86,400 104,400 H246 A23,23 0 0 1 246,446 H104 A23,23 0 0 0 104,492 H246")
// The liquid line takes in the coils' last U-bends as well.
private val LiquidPath = svg("M246,492 A23,23 0 0 1 246,538 H104 Q86,538 86,554 V576 Q86,600 110,600 H610 Q634,600 634,576 V554 Q634,538 616,538 H474 A23,23 0 0 1 474,492")
private val SuctionPath = svg("M474,492 H616 A23,23 0 0 0 616,446 H474 A23,23 0 0 1 474,400 H616 Q634,400 634,384 V172 Q634,128 590,128 H480")
private val HotChevrons = svg("M196,121 l-8,7 l8,7 M79,262 l7,8 l7,-8")
private val LiquidChevrons = svg("M354,593 l8,7 l-8,7")
private val SuctionChevrons = svg("M627,278 l7,-8 l7,8 M532,121 l-8,7 l8,7")
private val HeatWaves = svg(
    "M160,492 c-6,-8 6,-14 0,-22 c-6,-8 6,-14 0,-22 M175,494 c-6,-8 6,-14 0,-22 c-6,-8 6,-14 0,-22 c-4,-5 0,-9 0,-9 M190,492 c-6,-8 6,-14 0,-22 c-6,-8 6,-14 0,-22",
)
private val Snowflake = svg(
    "M545,444 V496 M522,457 L568,483 M522,483 L568,457 M538,450 L545,456 L552,450 M538,490 L545,484 L552,490 " +
        "M526,466 L534,465 L530,457 M564,474 L556,475 L560,483 M526,474 L534,475 L530,483 M564,466 L556,465 L560,457",
)
/** Air blown out of the condenser (to the left) and out of the evaporator
 * (to the right), one arrow per path, top to bottom. */
private val CondenserAir = listOf(446, 470, 494).map { y -> svg("M60,$y h-20 m6,-5 l-6,5 l6,5") }
private val EvaporatorAir = listOf(446, 470, 494).map { y -> svg("M660,$y h20 m-6,-5 l6,5 l-6,5") }
private val CompressorShell = svg("M315,118 Q315,90 365,88 Q415,90 415,118 V250 Q415,272 365,274 Q315,272 315,250 Z")
private val CompressorLines = svg(
    "M343,92 V62 M387,92 V62 M336,62 H350 M380,62 H394 M315,122 Q365,140 415,122 M315,123 H302 M315,133 H302 " +
        "M338,268 L318,292 M392,268 L412,292 M440,148 V136 Q440,124 452,124 H470 M450,148 V140 Q450,134 456,134 H470 " +
        "M445,242 V258 H415 M445,258 V264",
)

/** Rounded rectangles of the compressor drawing: (x, y, w, h, radius, filled). */
private val CompressorParts = listOf(
    floatArrayOf(292f, 116f, 10f, 24f, 2f, 1f),
    floatArrayOf(320f, 134f, 10f, 72f, 5f, 0f),
    floatArrayOf(298f, 290f, 34f, 8f, 2f, 0f),
    floatArrayOf(398f, 290f, 34f, 8f, 2f, 0f),
    floatArrayOf(430f, 168f, 30f, 74f, 13f, 1f),
    floatArrayOf(438f, 148f, 14f, 20f, 0f, 0f),
    floatArrayOf(434f, 155f, 22f, 7f, 2f, 0f),
    floatArrayOf(470f, 116f, 10f, 24f, 2f, 1f),
    floatArrayOf(415f, 196f, 15f, 10f, 0f, 0f),
)

private fun DrawScope.stroke(path: Path, color: Color, width: Float) =
    drawPath(path, color, style = Stroke(width, cap = StrokeCap.Round, join = StrokeJoin.Round))

/** How lit air arrow [i] of 3 is at [phase] (0..3, cycling): a light runs
 * down the stack, one arrow after another. */
internal fun arrowGlow(i: Int, phase: Float): Float {
    val d = kotlin.math.abs(((phase - i) % 3f + 4.5f) % 3f - 1.5f)
    return (1f - d).coerceIn(0f, 1f)
}

/** The air arrows, each between grey and its side's colour as the light passes. */
private fun DrawScope.drawAir(phase: Float) {
    for (i in 0..2) {
        val g = arrowGlow(i, phase)
        stroke(CondenserAir[i], lerp(Air, HotGas, g), 2.5f + g)
        stroke(EvaporatorAir[i], lerp(Air, Suction, g), 2.5f + g)
    }
}

/** Everything but the readings and the air, in the mockup's 720 x 640 units. */
private fun DrawScope.drawSchematic() {
    // Faint engineering grid.
    var g = 0f
    while (g <= W) { drawLine(GridLine, Offset(g, 0f), Offset(g, H), 1f); g += 24f }
    g = 0f
    while (g <= H) { drawLine(GridLine, Offset(0f, g), Offset(W, g), 1f); g += 24f }

    stroke(FinsPath, Fins, 2f)
    // Piping: a dark shell under a thinner coloured core.
    stroke(LoopPath, PipeShell, 9f)
    stroke(HotPath, HotGas, 4.5f)
    stroke(LiquidPath, LiquidLine, 4.5f)
    stroke(SuctionPath, Suction, 4.5f)
    stroke(HotChevrons, HotGas, 3f)
    stroke(LiquidChevrons, LiquidLine, 3f)
    stroke(SuctionChevrons, Suction, 3f)

    // Fan discs.
    for (cx in listOf(175f, 545f)) {
        drawCircle(Ground, 44f, Offset(cx, 470f))
        drawCircle(Equipment, 44f, Offset(cx, 470f), style = Stroke(2.5f))
        drawCircle(Equipment.copy(alpha = 0.35f), 36f, Offset(cx, 470f), style = Stroke(1.2f))
    }
    stroke(HeatWaves, HotGas, 3f)
    stroke(Snowflake, Suction, 3f)

    // Compressor: line art with a soft lift under it.
    drawPath(CompressorShell, Plate)
    for ((width, alpha) in listOf(7f to 0.08f, 2.5f to 1f)) {
        val c = Equipment.copy(alpha = alpha)
        stroke(CompressorShell, c, width)
        stroke(CompressorLines, c, width)
        for (r in CompressorParts) {
            if (alpha == 1f && r[5] == 1f) drawRoundRect(Plate, Offset(r[0], r[1]), Size(r[2], r[3]), CornerRadius(r[4]))
            drawRoundRect(c, Offset(r[0], r[1]), Size(r[2], r[3]), CornerRadius(r[4]), style = Stroke(width, join = StrokeJoin.Round))
        }
    }
}

/** The cycle, scaled to the card's width, with tappable instrument tags:
 * discharge, suction, compressor body and condenser. */
@Composable
internal fun CycleSchematic(cycle: CycleSensors, onOpenChart: (SensorResponse) -> Unit) {
    BoxWithConstraints(Modifier.fillMaxWidth().aspectRatio(W / H).padding(4.dp)) {
        val unit = maxWidth / W
        // The air arrows light up one after another, round and round.
        val phase by rememberInfiniteTransition(label = "air").animateFloat(
            initialValue = 0f,
            targetValue = 3f,
            animationSpec = infiniteRepeatable(tween(1800, easing = LinearEasing), RepeatMode.Restart),
            label = "airPhase",
        )
        Canvas(Modifier.fillMaxSize()) {
            val k = size.width / W
            scale(k, k, pivot = Offset.Zero) {
                drawSchematic()
                drawAir(phase)
            }
        }
        Tag(cycle.discharge, HotGas, HotGas, 140f, 44f, 116f, unit, onOpenChart)
        Tag(cycle.suction, Suction, Suction, 470f, 44f, 104f, unit, onOpenChart)
        Tag(cycle.compressor, Equipment, HotGas, 307f, 314f, 116f, unit, onOpenChart)
        Tag(cycle.condenser, LiquidLine, LiquidLine, 302f, 532f, 116f, unit, onOpenChart)
    }
}

/** An instrument tag: dark plate, thin edge in [edge], a tick in [tick] on
 * the left and the reading in white. Position and size in mockup units. */
@Composable
private fun Tag(
    sensor: SensorResponse?,
    edge: Color,
    tick: Color,
    x: Float,
    y: Float,
    width: Float,
    unit: Dp,
    onOpenChart: (SensorResponse) -> Unit,
) {
    val shape = RoundedCornerShape(unit * 8f)
    val fontSize = with(LocalDensity.current) { (unit * 30f).toSp() }
    Box(
        Modifier
            .offset(unit * x, unit * y)
            .size(unit * width, unit * 44f)
            .background(Plate, shape)
            .border(1.dp, edge.copy(alpha = 0.55f), shape)
            .quietClickable { sensor?.let(onOpenChart) },
        contentAlignment = Alignment.Center,
    ) {
        Box(
            Modifier
                .align(Alignment.CenterStart)
                .size(unit * 4f, unit * 20f)
                .background(tick, RoundedCornerShape(unit * 2f)),
        )
        Text(
            sensor?.let { Formatters.reading(it.current_temperature, it.unit) } ?: "—",
            color = Color(0xFFE8EEF6),
            style = TextStyle(fontFamily = Barlow, fontWeight = FontWeight.SemiBold, fontSize = fontSize, fontFeatureSettings = "tnum"),
            textAlign = TextAlign.Center,
            maxLines = 1,
            softWrap = false,
            modifier = Modifier.padding(start = unit * 6f),
        )
    }
}
