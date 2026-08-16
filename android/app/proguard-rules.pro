# Kotlinx serialization keeps its serializer() companions
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.AnnotationsKt
-keepclassmembers class kotlinx.serialization.json.** { *** Companion; }
-keepclasseswithmembers class pl.frigocore.service.data.model.** {
    *** Companion;
}
-keep,includedescriptorclasses class pl.frigocore.service.**$$serializer { *; }
-keepclassmembers class pl.frigocore.service.** {
    *** Companion;
}
-keepclasseswithmembers class pl.frigocore.service.** {
    kotlinx.serialization.KSerializer serializer(...);
}
