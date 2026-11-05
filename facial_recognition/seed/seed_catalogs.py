"""Papéis, permissões e equipes iniciais usados pela bancada."""
PERMISSIONS = {
    'teams.read': ('ADMIN', 'N1', 'N2', 'N3'),
    'agents.create': ('N1',),
    'agents.read': ('N1', 'N2'),
    'agents.update': ('N1', 'N2'),
    'agents.manage': ('N2',),
    'validations.read': ('N1', 'N2'),
    'validations.create': ('N2',),
    'analyses.write': ('N1',),
    'validations.share': ('N1', 'N2'),
    'validations.participants.manage': ('N2',),
    'validations.review': ('N2',),
    'reports.send': ('N2',),
    'reports.read': ('N2',),
    'vault.read': ('N3',),
    'vault.decide': ('N3',),
    'publications.publish': ('N3',),
    'publications.read': ('N3',),

    'accounts.request': ('ADMIN', 'N2', 'N3'),
    'accounts.request.read': ('ADMIN', 'N2', 'N3'),
    'accounts.manage': ('ADMIN',), 'accounts.approve': ('ADMIN',),
    'authorization.read': ('ADMIN',), 'audit.read': ('ADMIN',),
}


async def seed_catalogs(connection):
    """Insere papéis, permissões, vínculos e equipes iniciais que ainda faltam.

    Usa conflitos de chave para preservar registros existentes e não limpa soft_delete de
    vínculos desativados. Os códigos em PERMISSIONS cobrem as operações administrativas
    e científicas dos contratos atuais.

    Args:
        connection: Conexão PostgreSQL vinculada ao schema e à requisição atuais.

    Returns:
        None: Preenche o catálogo necessário para os fluxos atuais da bancada.
    """
    for role in ['ADMIN', 'N1', 'N2', 'N3']:
        await connection.execute('INSERT INTO roles(code,name) VALUES($1,$1) ON CONFLICT(code) DO NOTHING', role)
    for code, roles in PERMISSIONS.items():
        permission = await connection.fetchval('SELECT id FROM permissions WHERE code=$1', code)
        if permission is None:
            permission = await connection.fetchval('INSERT INTO permissions(code) VALUES($1) RETURNING id', code)
        for role in roles:
            await connection.execute('INSERT INTO role_permissions(role_id,permission_id) SELECT id,$2 FROM roles WHERE code=$1 ON CONFLICT DO NOTHING', role, permission)
    for code, name in [('A', 'Equipe A'), ('B', 'Equipe B')]:
        await connection.execute('INSERT INTO teams(code,name) VALUES($1,$2) ON CONFLICT(code) DO NOTHING', code, name)
