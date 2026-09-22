/** Small physical props, softly crossfaded by the same rig as the face. */
export function AmbientAccessories() {
  return (
    <>
      <span className="lia-weather lia-weather--rain">
        <svg viewBox="0 0 100 100" focusable="false">
          <g className="lia-weather-fall" stroke="#9ac8da" strokeWidth="3" strokeLinecap="round">
            <path d="M8 2L6 9M28 -5L26 2M78 -3L76 4M94 7L92 14" />
          </g>
          <path
            d="M51 16V84Q51 95 40 89"
            fill="none"
            stroke="#53656d"
            strokeWidth="4"
            strokeLinecap="round"
          />
          <path d="M7 48Q49 -9 94 47Q81 36 68 49Q52 35 36 49Q20 36 7 48Z" fill="currentColor" />
          <path
            d="M7 48Q49 -9 94 47M36 49Q40 20 51 15Q65 29 68 49"
            fill="none"
            stroke="#d0eced"
            strokeOpacity=".55"
            strokeWidth="2"
          />
        </svg>
      </span>
      <span className="lia-weather lia-weather--storm">
        <svg viewBox="0 0 110 95" focusable="false">
          <path
            d="M18 47C-2 44 2 22 22 22C25 0 55 -2 65 17C88 8 106 28 94 44Q89 49 77 48Z"
            fill="#718497"
          />
          <path
            d="M19 22Q38 12 44 26M65 17Q77 16 82 24"
            fill="none"
            stroke="#b4c3cc"
            strokeWidth="3"
            strokeLinecap="round"
            opacity=".6"
          />
          <path d="M57 42L43 65H55L45 84L76 56H60L69 42Z" fill="#f3d28a" />
          <g
            className="lia-weather-fall lia-weather-fall--slant"
            stroke="#9bbcd0"
            strokeWidth="3"
            strokeLinecap="round"
          >
            <path d="M21 53L15 65M37 51L31 63M88 53L82 65" />
          </g>
        </svg>
      </span>
      <span className="lia-weather lia-weather--cold">
        <svg viewBox="0 0 140 55" focusable="false">
          <path d="M14 8Q69 24 123 6L128 23Q72 42 12 25Z" fill="currentColor" />
          <path d="M89 21L119 17L120 47L96 50Z" fill="currentColor" />
          <path
            d="M18 14Q70 30 119 13M17 21Q70 37 122 20M96 31L116 28M98 38L116 35M99 45L117 42"
            fill="none"
            stroke="#d1e5e3"
            strokeOpacity=".45"
            strokeWidth="2"
          />
          <path d="M99 48V54M105 47V53M112 46V52M118 45V51" stroke="currentColor" strokeWidth="3" />
        </svg>
      </span>
      <span className="lia-weather lia-weather--freezing">
        <svg viewBox="0 0 150 70" focusable="false">
          <path
            d="M25 27Q39 11 58 8L55 17L47 15L43 27L36 24L30 33Z M126 41Q140 58 143 77L134 71L137 63L128 59L133 53Z"
            fill="#c5e8ec"
            stroke="#edfaff"
            strokeWidth="2"
            strokeLinejoin="round"
          />
          <path
            d="M32 24L47 15M36 18L38 24M131 50L137 65"
            fill="none"
            stroke="#9ed4e4"
            strokeWidth="3"
            strokeLinecap="round"
          />
          <g className="lia-weather-breath" fill="#d8eef2">
            <ellipse cx="132" cy="101" rx="10" ry="5" />
            <ellipse cx="143" cy="98" rx="7" ry="6" />
          </g>
        </svg>
      </span>
      <span className="lia-weather lia-weather--snow">
        <svg viewBox="0 0 150 100" focusable="false">
          <g
            className="lia-weather-fall lia-weather-fall--snow"
            fill="none"
            stroke="#d8eff5"
            strokeWidth="2"
            strokeLinecap="round"
          >
            <path d="M15 0V18M7 4L23 14M7 14L23 4M12 2L15 5L18 2M12 16L15 13L18 16" />
            <path d="M126 15V35M117 20L135 30M117 30L135 20M123 17L126 20L129 17M123 33L126 30L129 33" />
            <path d="M5 60V74M-1 63L11 71M-1 71L11 63" opacity=".7" />
          </g>
        </svg>
      </span>
      <span className="lia-weather lia-weather--hot">
        <svg viewBox="0 0 65 75" focusable="false">
          <g className="lia-weather-fan">
            <path d="M32 62L2 25Q31 -5 62 25Z" fill="#deb789" />
            <path
              d="M32 62L12 18M32 62L25 11M32 62L40 11M32 62L53 18"
              fill="none"
              stroke="#f5ddaf"
              strokeWidth="2"
            />
            <path d="M32 60V73" stroke="#947558" strokeWidth="4" strokeLinecap="round" />
          </g>
        </svg>
      </span>
      <span className="lia-weather lia-weather--heat">
        <svg viewBox="0 0 28 45" focusable="false">
          <g className="lia-weather-sweat">
            <path d="M14 3Q11 15 5 24C-4 43 30 45 23 25Q17 14 14 3Z" fill="#83bac8" />
            <path
              d="M10 22Q4 32 11 35"
              fill="none"
              stroke="#edf9ff"
              strokeWidth="3"
              strokeLinecap="round"
              opacity=".7"
            />
          </g>
        </svg>
      </span>
      <span className="lia-weather lia-weather--fog">
        <svg viewBox="0 0 160 45" focusable="false">
          <path
            d="M8 14Q39 1 72 15T146 13M22 26Q53 15 88 27T155 24M3 37Q35 27 69 38T136 35"
            fill="none"
            stroke="currentColor"
            strokeWidth="5"
            strokeLinecap="round"
          />
        </svg>
      </span>
      <span className="lia-weather lia-weather--wind">
        <svg viewBox="0 0 65 85" focusable="false">
          <path d="M48 9Q10 10 12 46Q37 60 48 9Z" fill="#9aaf75" />
          <path
            d="M19 40L43 16M19 40Q11 61 23 72"
            fill="none"
            stroke="#667a51"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
      </span>
      <span className="lia-weather lia-weather--night">
        <svg viewBox="0 0 65 65" focusable="false">
          <path d="M44 8A24 24 0 1 0 54 46A24 24 0 0 1 44 8Z" fill="#d9d9b5" />
          <path d="M48 19L50 25L56 27L50 29L48 35L46 29L40 27L46 25Z" fill="#f2eac8" opacity=".7" />
        </svg>
      </span>
    </>
  );
}
