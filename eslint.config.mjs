import js from '@eslint/js';
import globals from 'globals';

export default [
    {
        files: ['order_profitability_predictor/public/js/**/*.js', 'order_profitability_predictor/tests/*.cjs'],
        ...js.configs.recommended,
        languageOptions: {
            ecmaVersion: 2022,
            globals: {
                ...globals.browser,
                ...globals.node,
                frappe: 'readonly',
                __: 'readonly',
                format_currency: 'readonly',
                format_number: 'readonly',
            },
        },
        rules: {
            ...js.configs.recommended.rules,
            'no-console': 'error',
        },
    },
    {
        files: ['**/*.cjs'],
        languageOptions: {sourceType: 'commonjs'},
    },
];
