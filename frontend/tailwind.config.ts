import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#3363FF',
          hover: '#5580FF',
          active: '#1A4FE6',
          disabled: '#99B3FF',
          light: '#E6EDFF',
        },
        medical: {
          primary: '#0891B2',
          success: '#059669',
          light: '#ECFEFF',
        },
        semantic: {
          success: '#67C23A',
          warning: '#E6A23C',
          error: '#F56C6C',
          info: '#909399',
        },
        bg: {
          primary: '#FFFFFF',
          secondary: '#F7F8FA',
          tertiary: '#F0F2F5',
        },
      },
      borderRadius: {
        card: '12px',
        field: '8px',
      },
      fontFamily: {
        sans: ['PingFang SC', 'Microsoft YaHei', 'Noto Sans SC', 'sans-serif'],
      },
    },
  },
  plugins: [],
}

export default config
