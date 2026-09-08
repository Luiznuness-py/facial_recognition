``` mermaid
erDiagram
    FT_REGISTROS {
        integer ID_REGISTRO PK
        integer ID_USER FK
        integer ID_RECURSO FK
        timestamp DT_REGISTRO
    }

    DM_USUARIOS {
        integer ID_USER PK
        integer ID_VETOR FK
        integer ID_PERM FK
        integer ID_CARGO FK
        varchar NM_USER
        varchar DS_EMAIL
        integer NR_IDADE
    }

    DM_PERMISSOES {
        integer ID_PERM PK
        varchar NM_PERM
    }

    DM_VETORES {
        integer ID_VETOR PK
        varchar DS_VETOR
    }

    DM_CARGOS {
        integer ID_CARGO PK
        varchar DS_CARGO
    }

    DM_RECURSOS {
        integer ID_RECURSO PK
        varchar NM_RECURSO
        varchar DS_RECURSO
    }

    TB_COFRE {
        integer ID_AMEACA PK
        varchar DS_LINGUICA
    }

    TB_FLORESTAS {
        integer ID_FLORESTAS PK
        varchar DS_LINGUICA
    }

    TB_DIREITOS_ANIMAIS {
        integer ID_DIREITO PK
        varchar DS_LINGUICA
    }

    TB_AREAS_PROTECAO {
        integer ID_AREA PK
        varchar DS_LINGUICA
    }

    TB_BIODIVERSIDADE {
        integer ID_BIO PK
        varchar DS_LINGUICA
    }

    DM_PERMISSOES ||--o{ DM_USUARIOS : "possui"
    DM_VETORES ||--o{ DM_USUARIOS : "possui"
    DM_CARGOS ||--o{ DM_USUARIOS : "possui"
    DM_USUARIOS ||--o{ FT_REGISTROS : "realiza"
    DM_RECURSOS ||--o{ FT_REGISTROS : "é consultado"
```
