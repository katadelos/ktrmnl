import QtQuick 2.15

QtObject {
    property FontLoader displayFontLoader: FontLoader {
        source: Qt.resolvedUrl("../assets/fonts/KTRMNLDINMittelschrift-Regular.otf")
    }
    property FontLoader bodyFontLoader: FontLoader {
        source: Qt.resolvedUrl("../assets/fonts/NeueHaasDisplayRoman.ttf")
    }
    property FontLoader cjkFontLoader: FontLoader {
        source: Qt.resolvedUrl("../assets/fonts/NotoSansCJK-Regular.ttc")
    }

    property int viewportWidth: 800
    property int viewportHeight: 600
    property real textScale: 1.0
    property real rowHeightScale: 1.0
    property real keyboardHeightRatio: 0.43
    property string language: "en"
    enum InputMode { Touch, Navigation }
    property int inputMode: Theme.Touch
    readonly property bool navigationFocus: inputMode === Theme.Navigation

    property color paper: "#ffffff"
    property color ink: "#000000"
    readonly property color selectedPaper: ink
    readonly property color selectedInk: paper
    readonly property bool darkMode: paper.r + paper.g + paper.b < 1.5
    readonly property bool narrowPanel: Math.min(viewportWidth, viewportHeight) === 600
    readonly property color wash: darkMode ? "#151515" : "#f4f4f4"
    readonly property color selectedWash: darkMode ? "#f4f4f4" : "#151515"
    readonly property color secondary: darkMode
        ? (narrowPanel ? "#cccccc" : "#aaaaaa") : (narrowPanel ? "#333333" : "#555555")
    readonly property color selectedSecondary: darkMode
        ? (narrowPanel ? "#333333" : "#555555") : (narrowPanel ? "#cccccc" : "#aaaaaa")
    readonly property color outline: narrowPanel ? ink : (darkMode ? "#666666" : "#aaaaaa")
    readonly property color selectedOutline: narrowPanel
        ? selectedInk : (darkMode ? "#aaaaaa" : "#666666")

    // Layout follows the panel resolution; every text role shares the selected
    // profile's text scale so controls and content keep the same hierarchy.
    readonly property real scale: Math.max(
                                      0.86,
                                      Math.min(Math.max(viewportWidth, viewportHeight) / 800,
                                               Math.min(viewportWidth, viewportHeight) / 600))
    readonly property real boundedScale: Math.max(
                                             0.86,
                                             Math.min(1.15,
                                                      Math.min(viewportWidth, viewportHeight) / 600))
    readonly property real contentTextScale: boundedScale * textScale
    readonly property int outerMargin: Math.round(24 * scale)
    readonly property int compactMargin: Math.round(16 * scale)
    readonly property int headerTopInset: Math.round(10 * scale)
    readonly property int headerHeight: Math.round(68 * scale)
    readonly property int rowHeight: Math.round(58 * boundedScale * rowHeightScale)
    readonly property int divider: Math.max(1, Math.round(2 * scale))
    readonly property int controlBorderWidth: Math.max(1, Math.round(scale))
    readonly property int titleSize: Math.round(20.5 * contentTextScale)
    readonly property int headingSize: Math.round(17 * contentTextScale)
    readonly property int bodySize: Math.round(15.5 * contentTextScale)
    readonly property int detailSize: Math.round(12 * contentTextScale)
    readonly property int dialogBodySize: Math.round(13 * contentTextScale)
    readonly property int controlSize: Math.round(13 * contentTextScale)
    readonly property int fieldSize: Math.round(14.5 * contentTextScale)
    readonly property int hintSize: Math.round(10.5 * contentTextScale)
    readonly property int keyboardKeySize: Math.round(16 * contentTextScale)
    readonly property int keyboardNumberSize: Math.round(18.5 * contentTextScale)
    readonly property int keyboardSymbolSize: Math.round(12 * contentTextScale)
    readonly property bool usesCjkFont: language === "zh" || language === "ja"
    readonly property string displayFont: usesCjkFont
        ? cjkFontLoader.name : displayFontLoader.name
    readonly property string bodyFont: usesCjkFont
        ? cjkFontLoader.name : bodyFontLoader.name
}
